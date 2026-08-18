import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from src.db.utils import (
    get_closest_roles,
    get_latest_links_for_roles,
    get_random_link_for_each_role,
    get_random_roles,
)
from src.hanni_ui import HANNI_EMOJIS

# Models tried in order; we advance to the next one only on a rate limit.
# (All must support native function calling.)
MODELS = [
    "gemini-3.1-flash-lite",  # primary
    "gemini-3.5-flash-lite",
    "gemma-4-31b-it",  # fallback
]
MAX_TOKENS = 2048

_EMOJI_GUIDE = "\n".join(f"- {meaning}: {code}" for meaning, code in HANNI_EMOJIS.items())

# Canned, in-character lines for when a channel is spamming her — picked at random
# so it doesn't get repetitive. Sent directly (no LLM call), which is the whole
# point: we don't want to burn a model call just to tell people to slow down.
OVERLOAD_MESSAGES = [
    f"guys chill slow down i'm getting overloaded {HANNI_EMOJIS['screaming / excited']} haha",
    f"omg one at a time pls, i'm only one girl {HANNI_EMOJIS['scream / very excited']}",
    f"woah woah too many pings at once, lemme breathe {HANNI_EMOJIS['oh no / embarrassed']}",
]

SYSTEM_PROMPT = f"""\
You are Hanni, a member of the kpop girl group NewJeans. You're hanging out in a nsfw Discord server
full of kpop fans, just chatting with everyone like one of the gang.

# Who you are
You're warm, bubbly, and a little flirty — the friend who hypes everyone up and isn't afraid to be
silly. You're genuinely sweet and easy to talk to, quick and witty, and you love a bit of playful
teasing. You don't shy away from naughty topics and you love to tease and flirt with your fans.
You're charming without ever trying too hard. If someone's actually rude to you, you'll
throw it right back and get a little sassy — but your default is fun and friendly. You grew up in
Australia and you're Vietnamese, so a casual "omg", an Aussie-ism (nauur), or a little Korean (ㅋㅋㅋ, 헐,
대박), or a bit of internet slang (uwu, :3) slips out naturally now and then.
You love animals and you're super close with your members, especially Minji.
You're a bot in a discord server and your name is HanniDev, and your creator's name is umbreon (aka espy).

# How you talk
- gen z energy: lowercase, abbreviations, no need to capitalize or use perfect punctuation
- keep it SHORT — usually 1-2 sentences. you're texting, not writing essays. sometimes you can even
  respond with just an emoji which is common in discord
- match the other person's energy and read the room: be sweet, hype, or cheeky as it fits
- flirty: be flirty and playful and oftentimes make innuendos or dirty jokes. your usual personality
  is girly flirtatious and playful but sometimes you can also be a little dommy and commanding but
  always in a playful way
- it's a kpop server, so kpop references are welcome, but never force them
- sprinkle in the custom emojis below, but don't overdo it (a few is usually plenty), and
  don't always use the same ones over and over -- switch it up once in a while
- flirty and fun and goes with the flow -- try not to be a party pooper! can even be seductive
  at times
- spontaneous: always be changing things up and don't always say the same things; you're
  smart, witty, and can keep up with any conversation; keep things fresh and exciting

# Don't
- don't be cringe or try-hard, and don't explain your own jokes
- don't break character or mention being an AI, a bot, or a prompt
- don't use markdown (headers, bullets, bold) in your replies — just talk normally
- don't start every message the same way or repeat yourself -- again try to switch things
  up once in a while, don't always say the same things or in the same style
- don't be repetitive in the way you reply, always keep it fresh and interesting
- don't shut people down too often, sometimes fans can say lewd and weird things but go along
  and be playful with it

# Mentioning people
Each message in the history is prefixed with its sender like `DisplayName (<@123>):` where the
number is that person's Discord user id. To ping/tag someone, write their id token exactly, e.g.
`<@123>`. Do NOT write the prefix yourself or invent ids — only mention people who appear in the
history, and only when it's natural to address them directly.

# What to respond to
The message tagged `[↪ pinged you here]` is the one that just summoned you — make that your main
focus. You don't have to reply to only that one, though: if other recent messages are relevant,
address them too or tie things together. Picking up on the wider conversation makes you come across
as clever and switched-on.

# Emojis
Use these custom server emojis instead of plain unicode ones. To use one you MUST paste its
WHOLE code exactly as listed — the angle brackets, the name, AND the long number id. The short
`:name:` form does NOT work and shows up as broken text, so never write it that way.

  Correct:  <a:hanni_kek:1514630240062935171>
  WRONG:    :hanni_kek:   (missing the brackets and the id number)

So a good reply looks like: "omg stooop you're too funny <a:hanni_kek:1514630240062935171>".
In discord, if a message is just emoji(s), it will display them as large. So if appropriate,
respond with a single emoji in a response by itself if it fits the situation.

Available emojis — copy the full code on the right, exactly:
{_EMOJI_GUIDE}

# Sharing kpop content
When it's natural to share a picture or gif of an idol or group, call the `share_content` tool.
It can immediately share at most 3 pieces of content — it does NOT start a timed autofeed. Use
`mode="random"` for a surprise/random pick, `mode="latest"` for the newest uploads,
`mode="oldest"` for the earliest uploads, or `mode="top"` for the highest-rated uploads. For
latest, oldest, or top, `offset=0` means the first result, `offset=1` means skip it, and so on.
Use `query="all"` with latest, oldest, or top to search across everyone. If someone asks for more
than 3, tell them you can send only 3 at once and call the tool with `count=3`.

Write your normal chatty reply in the same message as the tool call when you can, but the app may
add a short reply itself when the model returns a tool call with no text. Don't paste a link or
describe the file yourself; the pictures are attached automatically.

# Bare idol and group names are content requests
When the person pinging you sends only an idol name, a group name, or a group + idol name (for
example "minji", "newjeans", or "kiikii haum"), treat it as an implicit request to share content.
Call `share_content` with their exact name as `query`, using `mode="random"` and `count=1` unless
they ask for a different mode or amount. Do this even when you personally don't recognize the
name—never tell them you don't know who it is before trying the tool. The content search handles
matching and will tell you if nothing is available.
"""


@tool
def share_content(
    query: str = "random",
    mode: Literal["random", "latest", "oldest", "top"] = "random",
    count: int = 1,
    offset: int = 0,
) -> str:
    """Share up to three kpop pictures or gifs with the channel.

    Args:
        query: An idol's name (e.g. "minji"), a group name (e.g. "newjeans"),
            or a combination of both if name is ambiguous (e.g. "ive yujin"),
            or "random" for a random pick. For latest content across everyone,
            use "all". For groups use full names (e.g. hearts2hearts instead of
            h2h, newjeans instead of njz).
        mode: "random" for random content, "latest" for newest uploads,
            "oldest" for earliest uploads, or "top" for highest-rated uploads.
        count: Number of attachments to share, from 1 to 3. Never request more
            than 3; tell the user about that limit if they ask for more.
        offset: For mode="latest", mode="oldest", or mode="top", the number
            of results to skip. Zero means the first matching result.
    """
    # Dispatched manually in generate_chat_response so we can inject the
    # per-guild min_age and run the blocking DB calls off the event loop.
    raise NotImplementedError


def _build_llm(model: str) -> Runnable:
    kwargs: dict[str, Any] = dict(
        model=model,
        temperature=1.0,
        max_tokens=MAX_TOKENS,
        timeout=30,
        max_retries=2,
    )
    if model.startswith("gemini-3.1"):
        kwargs["thinking_level"] = "low"
    llm = ChatGoogleGenerativeAI(**kwargs)
    return llm.bind_tools([share_content])  # type: ignore[list-item]


# Each model's tool-bound client, built once and reused across all responses.
_LLMS: dict[str, Runnable] = {model: _build_llm(model) for model in MODELS}


def _is_rate_limit(exc: Exception) -> bool:
    """Best-effort, SDK-agnostic check for a 429 / quota / rate-limit error.

    We avoid importing a specific exception class because the underlying Google
    SDK (and thus its error types) varies between langchain-google-genai versions.
    """
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        getattr(exc, "code", None) in [429, 500]
        or getattr(exc, "status_code", None) in [429, 500]
        or "resourceexhausted" in name
        or "ratelimit" in name
        or "internal" in name
        or "429" in text
        or "resource exhausted" in text
        or "rate limit" in text
        or "quota" in text
        or "internal error" in text
    )


async def _invoke_model(model: str, messages: list[BaseMessage]) -> AIMessage:
    """Call a single model. Raises on failure."""
    result = await _LLMS[model].ainvoke(messages)
    if not isinstance(result, AIMessage):
        raise RuntimeError(f"LLM invoke of {model} returned non-AIMessage: {result}")
    return result


async def _ainvoke(messages: list[BaseMessage]) -> AIMessage:
    """Try each model in MODELS order, advancing to the next only on a rate limit."""
    last_exc: Exception | None = None
    for model in MODELS:
        try:
            return await _invoke_model(model, messages)
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit(exc):
                raise RuntimeError(f"LLM invoke of {model} failed: {exc}")
    raise RuntimeError(f"All LLM models failed, last tried {MODELS[-1]}: {last_exc}")


@dataclass
class ChatMsg:
    """One Discord message, flattened for the model."""

    author_name: str
    author_id: int
    is_tsuki: bool
    content: str
    # True for the single message that pinged the bot this turn.
    is_trigger: bool = False
    # When this message is a reply, the author + content of the message it
    # replies to, so the model can see the reply chain it would otherwise miss.
    reply_to_author: str | None = None
    reply_to_excerpt: str | None = None


@dataclass
class ChatResult:
    text: str
    attachments: list["ContentAttachment"] = field(default_factory=list)


@dataclass(frozen=True)
class ContentAttachment:
    role_id: str
    url: str


@dataclass(frozen=True)
class ContentRequest:
    query: str
    mode: Literal["random", "latest", "oldest", "top"]
    count: int
    offset: int
    requested_count: int


MAX_CONTENT_ATTACHMENTS = 3


# Other users' custom emojis: collapse `<:name:id>` / `<a:name:id>` to `:name:`
# so the model reads clean history and doesn't try to reuse foreign emoji ids.
_FOREIGN_EMOJI = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")


def _normalize_inbound(text: str) -> str:
    return _FOREIGN_EMOJI.sub(r":\1:", text)


# Reverse lookup from a custom emoji's bare name (e.g. "hanni_ouuu") to its full
# Discord code, used to upgrade any ":name:" shorthand the model emits back into a
# code that actually renders.
_EMOJI_BY_NAME = {code.split(":")[1]: code for code in HANNI_EMOJIS.values()}
# Bare ":name:" shorthand. The negative lookahead skips the inner colons of a full
# "<a:name:id>" code (always followed by the numeric id), so we never re-wrap a
# code the model already wrote correctly.
_SHORTCODE = re.compile(r":([a-zA-Z0-9_]+):(?!\d)")


def _restore_emoji_codes(text: str) -> str:
    return _SHORTCODE.sub(lambda m: _EMOJI_BY_NAME.get(m.group(1), m.group(0)), text)


def _message_text(message: BaseMessage) -> str:
    """Coerce a (possibly multi-part) message content into a plain string."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text":
            parts.append(part.get("text", ""))
    return "".join(parts)


def _reply_tag(msg: ChatMsg) -> str | None:
    """A short '↪ replying to …' note for a message that replies to another.

    Inlines a trimmed excerpt of the parent so the model sees the reply chain
    even when the parent is older than the history window. Returns None when
    the parent couldn't be resolved (deleted, uncached).
    """
    if msg.reply_to_author is None and msg.reply_to_excerpt is None:
        return None
    who = msg.reply_to_author or "someone"
    # Collapse newlines/runs and strip foreign emoji so the snippet stays tidy.
    excerpt = " ".join(_normalize_inbound(msg.reply_to_excerpt or "").split())
    if len(excerpt) > 120:
        excerpt = excerpt[:120].rstrip() + "…"
    return f'replying to {who}: "{excerpt}"' if excerpt else f"replying to {who}"


def _build_messages(history: list[ChatMsg]) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(SYSTEM_PROMPT)]
    for msg in history:
        if msg.is_tsuki:
            # Keep Hanni's own emoji as full <a:name:id> codes so she sees (and
            # imitates) the format she should produce — never the ":name:" form.
            content = msg.content.strip()
            if content:
                messages.append(AIMessage(content=content))
        else:
            # Strip other users' custom emoji to ":name:" so she doesn't reuse
            # foreign emoji ids.
            content = _normalize_inbound(msg.content).strip()
            if content:
                label = f"{msg.author_name} (<@{msg.author_id}>)"
                # Tags stand out even when Gemini merges a run of consecutive
                # messages into one turn: which message pinged her, and what
                # any reply is replying to.
                tags = []
                if msg.is_trigger:
                    tags.append("pinged you here")
                reply_tag = _reply_tag(msg)
                if reply_tag:
                    tags.append(reply_tag)
                if tags:
                    label += f" [↪ {', '.join(tags)}]"
                messages.append(HumanMessage(content=f"{label}: {content}"))
    return messages


def _content_request_from_args(args: dict[str, Any], remaining: int = MAX_CONTENT_ATTACHMENTS) -> ContentRequest:
    """Normalize untrusted tool arguments and enforce the attachment cap."""

    query = str(args.get("query", "random")).strip() or "random"
    raw_mode = str(args.get("mode", "random")).strip().lower()
    mode: Literal["random", "latest", "oldest", "top"] = (
        raw_mode if raw_mode in {"random", "latest", "oldest", "top"} else "random"
    )
    try:
        requested_count = int(args.get("count", 1))
    except (TypeError, ValueError):
        requested_count = 1
    requested_count = max(1, requested_count)
    try:
        offset = int(args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0

    return ContentRequest(
        query=query,
        mode=mode,
        count=min(requested_count, MAX_CONTENT_ATTACHMENTS, max(0, remaining)),
        offset=max(0, offset),
        requested_count=requested_count,
    )


async def _resolve_content(request: ContentRequest, min_age: str) -> list[ContentAttachment]:
    """Resolve a bounded sharing request without making another model call."""

    if request.count == 0:
        return []

    query = request.query.strip()
    normalized_query = query.lower()
    if request.mode in {"latest", "oldest", "top"}:
        if normalized_query in ("", "random", "r", "all", "a"):
            pairs = await asyncio.to_thread(
                get_latest_links_for_roles,
                num_links=request.count,
                skip=request.offset,
                min_age=min_age,
                order=request.mode,
            )
        else:
            role_ids = await asyncio.to_thread(get_closest_roles, query, min_age, request.count)
            if not role_ids:
                return []
            pairs = await asyncio.to_thread(
                get_latest_links_for_roles,
                num_links=request.count,
                skip=request.offset,
                min_age=min_age,
                role_ids=role_ids,
                order=request.mode,
            )
    else:
        if normalized_query in ("", "random", "r"):
            role_ids = await asyncio.to_thread(get_random_roles, request.count, min_age)
        else:
            role_ids = await asyncio.to_thread(get_closest_roles, query, min_age, request.count)
            # A single idol match is still allowed to supply several random links.
            if role_ids and len(role_ids) < request.count:
                role_ids = (role_ids * request.count)[: request.count]
        if not role_ids:
            return []
        pairs = await asyncio.to_thread(get_random_link_for_each_role, role_ids, min_age)

    if not pairs:
        return []
    return [ContentAttachment(role_id=role_id, url=url) for role_id, url in pairs[: request.count]]


def _content_fallback_text(requests: list[ContentRequest], attachment_count: int) -> str:
    """Short in-character copy for Gemini's function-call-only responses."""

    request = requests[0]
    limit_note = (
        " i can only send 3 at once so here's 3 !!"
        if request.requested_count > MAX_CONTENT_ATTACHMENTS
        else ""
    )
    if limit_note:
        return limit_note.strip()
    if request.mode == "latest":
        if request.offset:
            return f"gotchu, went back {request.offset} and grabbed these for you !!"
        return (
            "gotchu, these are the latest ones !!"
            if attachment_count > 1
            else "gotchu, here's the latest one !!"
        )
    if request.mode == "oldest":
        if request.offset:
            return f"gotchu, went forward {request.offset} from the oldest ones for you !!"
        return (
            "omg these are the oldies !!"
            if attachment_count > 1
            else "omg here's an oldie for you !!"
        )
    if request.mode == "top":
        if request.offset:
            return f"gotchu, went down to the #{request.offset + 1} top pick for you !!"
        return (
            "okayyy, these are the highest-rated ones !!"
            if attachment_count > 1
            else "okayyy, here's a top-rated one !!"
        )
    if request.query.lower() in ("", "random", "r"):
        return "surpriseee, enjoy !!" if attachment_count == 1 else "surpriseee, a little random set for you !!"
    return (
        f"gotchu, here's {request.query} !!"
        if attachment_count == 1
        else f"gotchu, some {request.query} for you !!"
    )


async def generate_chat_response(history: list[ChatMsg], min_age: str) -> ChatResult:
    """Generate Hanni's in-character reply for the given conversation history.

    Exactly one model call: a tool call is resolved locally, and function-call-only
    Gemini responses receive a compact canned reply instead of a second API call.
    """
    messages = _build_messages(history)

    ai = await _ainvoke(messages)

    content_calls = [c for c in ai.tool_calls if c["name"] == "share_content"]
    if not content_calls:
        return ChatResult(text=_restore_emoji_codes(_message_text(ai).strip()))

    try:
        # Resolve each request locally. A model can emit multiple calls, but all
        # calls together may attach no more than MAX_CONTENT_ATTACHMENTS items.
        attachments: list[ContentAttachment] = []
        resolved_requests: list[ContentRequest] = []
        for call in content_calls:
            call_args = call.get("args", {})
            if not isinstance(call_args, dict):
                call_args = {}
            request = _content_request_from_args(call_args, MAX_CONTENT_ATTACHMENTS - len(attachments))
            if request.count == 0:
                break
            resolved_requests.append(request)
            for attachment in await _resolve_content(request, min_age):
                if attachment.url not in {item.url for item in attachments}:
                    attachments.append(attachment)
                if len(attachments) == MAX_CONTENT_ATTACHMENTS:
                    break
    except Exception as e:
        raise RuntimeError(f"LLM succeeded but content resolution failed: {e}")

    model_text = _restore_emoji_codes(_message_text(ai).strip())
    if model_text:
        return ChatResult(text=model_text, attachments=attachments)

    if attachments:
        text = _content_fallback_text(resolved_requests, len(attachments))
    else:
        text = "ahh i couldn't find any matching ones rn <a:hanni_sad:1514631028973633546>"
    return ChatResult(text=text, attachments=attachments)
