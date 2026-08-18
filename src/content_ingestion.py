"""Classify Discord content messages for the live updater."""

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

SUPPORTED_VIDEO_EMBED_TYPES = frozenset({"gifv", "video"})
ANIMATED_MEDIA_FLAG = 1 << 5
URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
ROLE_MENTION_PATTERN = re.compile(r"<@&(\d+)>")
ROOT: Literal["root"] = "root"
REPLY_CONTINUATION: Literal["reply_continuation"] = "reply_continuation"
UNTHREADED_CONTINUATION: Literal["unthreaded_continuation"] = "unthreaded_continuation"
SourceKind = Literal["root", "reply_continuation", "unthreaded_continuation"]
DEFAULT_CONTEXT_CACHE_SIZE = 10_000


@dataclass(frozen=True)
class ContentLinkDraft:
    """A single content link with the Discord provenance that produced it."""

    role_id: str
    author_id: str
    author: str
    uploaded_date: datetime
    url: str
    source_message_id: str
    root_message_id: str
    source_kind: SourceKind
    initial_reaction_count: int = 0


@dataclass(frozen=True)
class ContentContext:
    root_message_id: str
    role_ids: tuple[str, ...]
    author_id: str
    last_timestamp: datetime


def media_urls(message: dict[str, Any]) -> list[str]:
    """Return unique URLs from video embeds and explicitly animated image embeds."""

    urls: list[str] = []
    seen: set[str] = set()
    for embed in message.get("embeds", []):
        if not isinstance(embed, dict):
            continue
        embed_type = embed.get("type")
        if embed_type not in SUPPORTED_VIDEO_EMBED_TYPES and not _is_animated_image_embed(embed):
            continue
        url = embed.get("url")
        if isinstance(url, str) and url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _is_animated_image_embed(embed: dict[str, Any]) -> bool:
    if embed.get("type") != "image":
        return False
    for field in ("image", "thumbnail"):
        media = embed.get(field)
        flags = media.get("flags") if isinstance(media, dict) else None
        if isinstance(flags, int) and flags & ANIMATED_MEDIA_FLAG:
            return True
    return False


def role_mentions(message: dict[str, Any]) -> tuple[str, ...]:
    roles = message.get("mention_roles", [])
    if not isinstance(roles, list):
        return ()
    return tuple(dict.fromkeys(str(role_id) for role_id in roles if isinstance(role_id, (str, int))))


def text_role_mentions(message: dict[str, Any], known_role_ids: frozenset[str]) -> tuple[str, ...]:
    """Recover role mentions omitted from Discord's structured message payload."""

    content = message.get("content", "")
    if not isinstance(content, str):
        return ()
    return tuple(
        dict.fromkeys(role_id for role_id in ROLE_MENTION_PATTERN.findall(content) if role_id in known_role_ids)
    )


def reaction_count(message: dict[str, Any]) -> int:
    total = 0
    for reaction in message.get("reactions", []):
        if isinstance(reaction, dict):
            total += int(reaction.get("count", 0) or 0)
    return total


def is_url_only_content(message: dict[str, Any]) -> bool:
    """Allow unthreaded continuations only when their text is just URLs/whitespace."""

    content = message.get("content", "")
    if not isinstance(content, str):
        return False
    return not URL_PATTERN.sub("", content).strip()


def referenced_message_id(message: dict[str, Any]) -> str | None:
    reference = message.get("message_reference")
    if not isinstance(reference, dict):
        return None
    message_id = reference.get("message_id")
    return str(message_id) if isinstance(message_id, (str, int)) else None


class ContentMessageClassifier:
    """Classify role-tagged roots and their safe media continuations."""

    def __init__(
        self,
        continuation_window: timedelta = timedelta(minutes=2),
        context_cache_size: int = DEFAULT_CONTEXT_CACHE_SIZE,
        fallback_role_ids: frozenset[str] = frozenset(),
    ):
        if context_cache_size < 1:
            raise ValueError("context_cache_size must be at least 1")
        self.continuation_window = continuation_window
        self.context_cache_size = context_cache_size
        self.fallback_role_ids = fallback_role_ids
        self._active_by_author: dict[str, ContentContext] = {}
        self._context_by_message_id: OrderedDict[str, ContentContext] = OrderedDict()

    def _remember_context(self, message_id: str, context: ContentContext) -> None:
        self._context_by_message_id[message_id] = context
        self._context_by_message_id.move_to_end(message_id)
        if len(self._context_by_message_id) > self.context_cache_size:
            self._context_by_message_id.popitem(last=False)

    @staticmethod
    def _author_id(message: dict[str, Any]) -> str | None:
        author = message.get("author")
        if not isinstance(author, dict):
            return None
        author_id = author.get("id")
        return str(author_id) if isinstance(author_id, (str, int)) else None

    @staticmethod
    def _author_name(message: dict[str, Any]) -> str:
        author = message.get("author")
        if not isinstance(author, dict):
            return ""
        username = author.get("username")
        return username if isinstance(username, str) else ""

    @staticmethod
    def _message_id(message: dict[str, Any]) -> str | None:
        message_id = message.get("id")
        return str(message_id) if isinstance(message_id, (str, int)) else None

    @staticmethod
    def _timestamp(message: dict[str, Any]) -> datetime | None:
        timestamp = message.get("timestamp")
        if not isinstance(timestamp, str):
            return None
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _context_from_root(self, message: dict[str, Any]) -> ContentContext | None:
        roles = role_mentions(message) or text_role_mentions(message, self.fallback_role_ids)
        author_id = self._author_id(message)
        message_id = self._message_id(message)
        timestamp = self._timestamp(message)
        if not roles or not media_urls(message) or not author_id or not message_id or timestamp is None:
            return None
        return ContentContext(message_id, roles, author_id, timestamp)

    def _referenced_context(self, message: dict[str, Any]) -> ContentContext | None:
        parent_id = referenced_message_id(message)
        if parent_id and parent_id in self._context_by_message_id:
            return self._context_by_message_id[parent_id]

        referenced = message.get("referenced_message")
        if not isinstance(referenced, dict):
            return None
        context = self._context_from_root(referenced)
        if context is not None:
            self._remember_context(context.root_message_id, context)
        return context

    @staticmethod
    def _within_window(context: ContentContext, timestamp: datetime, window: timedelta) -> bool:
        elapsed = timestamp - context.last_timestamp
        return timedelta(0) <= elapsed <= window

    def _drafts(
        self,
        message: dict[str, Any],
        context: ContentContext,
        source_kind: SourceKind,
        urls: list[str],
        message_id: str,
        timestamp: datetime,
        author_id: str,
    ) -> list[ContentLinkDraft]:
        return [
            ContentLinkDraft(
                role_id=role_id,
                author_id=author_id,
                author=self._author_name(message),
                uploaded_date=timestamp,
                url=url,
                source_message_id=message_id,
                root_message_id=context.root_message_id,
                source_kind=source_kind,
                initial_reaction_count=reaction_count(message),
            )
            for role_id in context.role_ids
            for url in urls
        ]

    def consume(self, message: dict[str, Any]) -> list[ContentLinkDraft]:
        """Consume one chronological message and return any links safe to ingest."""

        author_id = self._author_id(message)
        message_id = self._message_id(message)
        timestamp = self._timestamp(message)
        if not author_id or not message_id or timestamp is None:
            return []

        urls = media_urls(message)
        roles = role_mentions(message) or text_role_mentions(message, self.fallback_role_ids)
        if roles and urls:
            context = ContentContext(message_id, roles, author_id, timestamp)
            self._active_by_author[author_id] = context
            self._remember_context(message_id, context)
            return self._drafts(message, context, ROOT, urls, message_id, timestamp, author_id)

        if not urls:
            self._active_by_author.pop(author_id, None)
            return []

        if roles:
            self._active_by_author.pop(author_id, None)
            return []

        parent_id = referenced_message_id(message)
        if parent_id is not None:
            context = self._referenced_context(message)
            if context is None or context.author_id != author_id:
                self._active_by_author.pop(author_id, None)
                return []
            continuation = ContentContext(context.root_message_id, context.role_ids, author_id, timestamp)
            self._active_by_author[author_id] = continuation
            self._remember_context(message_id, continuation)
            return self._drafts(message, continuation, REPLY_CONTINUATION, urls, message_id, timestamp, author_id)

        context = self._active_by_author.get(author_id)
        if (
            context is None
            or not is_url_only_content(message)
            or not self._within_window(context, timestamp, self.continuation_window)
        ):
            self._active_by_author.pop(author_id, None)
            return []

        continuation = ContentContext(context.root_message_id, context.role_ids, author_id, timestamp)
        self._active_by_author[author_id] = continuation
        self._remember_context(message_id, continuation)
        return self._drafts(message, continuation, UNTHREADED_CONTINUATION, urls, message_id, timestamp, author_id)
