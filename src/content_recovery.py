#!/usr/bin/env python3
"""Recover, transform, re-upload, and replace broken Imgur content links.

The script first tries the direct Imgur media URL. If that fails, it searches
Discord for the requested URL and tries the media URLs recorded in its embed.

Usage:
    python scripts/recover_content.py https://imgur.com/t5wnHGu
    python scripts/recover_content.py batch --role-id 1000863360776147054 --limit 50 --apply

By default this uses USER_AUTH from the repository's .env, matching this
repository's existing historical-fetch job, and searches the KPF channel.
TOKEN/DISCORD_TOKEN are used when USER_AUTH is absent; use --auth-env to
select one explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GUILD_ID = "124767749099618304"
DEFAULT_CHANNEL_ID = "124767749099618304"
DISCORD_API_BASE = "https://discord.com/api/v10"
IMGUR_API_BASE = "https://api.imgur.com/3"
MEDIA_EXTENSIONS = (".mp4", ".webm", ".gif", ".jpg", ".jpeg", ".png", ".webp")
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
IMGUR_DELETED_PLACEHOLDER_SIZE = 503
IMGUR_DELETED_PLACEHOLDER_DIMENSIONS = (161, 81)
VIDEO_EXTENSIONS = (".mp4", ".webm", ".gif")


@dataclass(frozen=True)
class MediaCandidate:
    url: str
    label: str


@dataclass(frozen=True)
class DownloadedMedia:
    path: Path
    content_type: str
    size: int
    recovery_method: str | None = None


@dataclass(frozen=True)
class UploadedMedia:
    media_id: str
    url: str
    deletehash: str | None
    processing_status: str | None


def trimmed_output_path(input_path: Path, force: bool) -> Path:
    destination = input_path.with_name(f"{input_path.stem}_trimmed.mp4")
    if force or not destination.exists():
        return destination

    counter = 2
    while True:
        candidate = input_path.with_name(f"{input_path.stem}_trimmed-{counter}.mp4")
        if not candidate.exists():
            return candidate
        counter += 1


def trim_first_frame(input_path: Path, force: bool) -> Path:
    """Remove only the first video frame and return a new MP4 path."""

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for the frame-trimming pipeline step")
    if input_path.suffix.lower() not in VIDEO_EXTENSIONS:
        suffix = input_path.suffix.lower() or "unknown media"
        raise RuntimeError(f"First-frame trimming requires video media; recovered file is {suffix}")

    output_path = trimmed_output_path(input_path, force)
    temporary_path = output_path.with_name(f".{output_path.stem}.part.mp4")
    temporary_path.unlink(missing_ok=True)

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "select='gte(n,1)',setpts=N/FRAME_RATE/TB",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(temporary_path),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        temporary_path.replace(output_path)
    except FileNotFoundError as error:
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg is required for the frame-trimming pipeline step") from error
    except subprocess.CalledProcessError as error:
        temporary_path.unlink(missing_ok=True)
        detail = error.stderr.strip() or "ffmpeg returned a non-zero exit status"
        raise RuntimeError(f"Could not trim the first frame: {detail}") from error

    return output_path


def parse_single_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover one Imgur URL and trim its first video frame.",
        usage="%(prog)s URL [options]\n       %(prog)s batch [options]",
    )
    parser.add_argument("url", help="A single imgur.com or i.imgur.com URL")
    parser.add_argument(
        "--channel-id",
        default=DEFAULT_CHANNEL_ID,
        help=f"Discord channel to search (default: {DEFAULT_CHANNEL_ID})",
    )
    parser.add_argument(
        "--guild-id",
        default=DEFAULT_GUILD_ID,
        help=f"Discord guild containing the channel (default: {DEFAULT_GUILD_ID})",
    )
    parser.add_argument(
        "--auth-env",
        choices=("TOKEN", "DISCORD_TOKEN", "USER_AUTH"),
        help="Environment variable containing Discord credentials",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="With --history-fallback, stop after this many 100-message pages",
    )
    parser.add_argument(
        "--history-fallback",
        action="store_true",
        help="Fall back to walking channel history if indexed message search finds nothing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing output file with the same name",
    )
    parser.add_argument(
        "--dump-search",
        action="store_true",
        help="Print the raw Discord guild-message-search response and exit",
    )
    return parser.parse_args(argv)


def extract_imgur_id(raw_url: str) -> str:
    """Return the case-sensitive Imgur media ID from a simple Imgur URL."""

    parsed = urlparse(raw_url.strip())
    host = parsed.hostname.lower() if parsed.hostname else ""
    if parsed.scheme not in {"http", "https"} or host not in {"imgur.com", "www.imgur.com", "i.imgur.com"}:
        raise ValueError("URL must point to imgur.com or i.imgur.com")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not parts:
        raise ValueError("Imgur URL does not contain a media ID")
    if parts[0].lower() in {"a", "album", "gallery"}:
        raise ValueError("Album/gallery URLs are not supported; provide the individual media URL")

    match = re.fullmatch(
        r"(?P<media_id>[A-Za-z0-9]{3,})(?:\.(?:mp4|webm|gifv|gif|jpg|jpeg|png|webp))?",
        parts[-1],
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError("Could not determine an Imgur media ID from the URL")
    return match.group("media_id")


def search_url_forms(raw_url: str) -> tuple[str, ...]:
    """Return exact URL forms worth matching in message/embed fields."""

    url = raw_url.strip()
    forms = {url, url.rstrip("/")}
    if url.startswith("https://"):
        forms.add("http://" + url[len("https://") :])
    elif url.startswith("http://"):
        forms.add("https://" + url[len("http://") :])
    return tuple(form for form in forms if form)


def auth_header(auth_env: str | None) -> tuple[str, str]:
    """Load credentials without exposing their value in logs."""

    selected_env = auth_env or os.getenv("RECOVERY_AUTH_ENV")
    if selected_env:
        value = os.getenv(selected_env, "").strip()
        if not value:
            raise RuntimeError(f"{selected_env} is empty or not present in .env")
    else:
        selected_env = next(
            (name for name in ("USER_AUTH", "TOKEN", "DISCORD_TOKEN") if os.getenv(name, "").strip()),
            None,
        )
        if selected_env is None:
            raise RuntimeError("Set TOKEN, DISCORD_TOKEN, or USER_AUTH in .env")
        value = os.environ[selected_env].strip()

    if selected_env in {"TOKEN", "DISCORD_TOKEN"} and not value.lower().startswith(("bot ", "bearer ")):
        value = f"Bot {value}"
    return value, selected_env


class DiscordClient:
    def __init__(self, authorization: str | None = None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "tsuki-bot-content-recovery/1.0"})
        if authorization:
            self.session.headers.update({"Authorization": authorization})

    def get_messages(self, channel_id: str, before: str | None) -> list[dict]:
        params: dict[str, str | int] = {"limit": 100}
        if before:
            params["before"] = before

        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
        for attempt in range(6):
            response = self.session.get(url, params=params, timeout=(10, 60))
            if response.status_code == 429:
                if attempt == 5:
                    raise RuntimeError("Discord rate-limited the search too many times")
                try:
                    retry_after = float(response.json().get("retry_after", 1))
                except (ValueError, TypeError):
                    retry_after = 1.0
                time.sleep(max(retry_after, 0.1))
                continue

            if response.status_code == 401:
                raise RuntimeError("Discord rejected the credentials (401); check TOKEN/USER_AUTH in .env")
            if response.status_code == 403:
                raise RuntimeError("Discord denied channel history (403); check channel permissions")
            if response.status_code == 404:
                raise RuntimeError(f"Discord could not find channel {channel_id} (404)")
            response.raise_for_status()

            messages = response.json()
            if not isinstance(messages, list):
                raise RuntimeError("Discord returned an unexpected message-history response")
            return messages

        raise RuntimeError("Discord request failed after retries")

    def search_messages(self, guild_id: str, channel_id: str, content: str) -> dict:
        """Search Discord's indexed guild messages for the exact URL text."""

        url = f"{DISCORD_API_BASE}/guilds/{guild_id}/messages/search"
        params = [
            ("content", content),
            ("channel_id", channel_id),
            ("limit", "25"),
            ("include_nsfw", "true"),
        ]

        for attempt in range(6):
            response = self.session.get(url, params=params, timeout=(10, 60))
            if response.status_code == 429:
                if attempt == 5:
                    raise RuntimeError("Discord rate-limited the search too many times")
                try:
                    retry_after = float(response.json().get("retry_after", 1))
                except (ValueError, TypeError):
                    retry_after = 1.0
                time.sleep(max(retry_after, 0.1))
                continue

            payload = response.json()
            if response.status_code == 202:
                if attempt == 5:
                    return payload
                retry_after = payload.get("retry_after", 1) if isinstance(payload, dict) else 1
                time.sleep(max(float(retry_after or 1), 0.1))
                continue

            if response.status_code == 401:
                raise RuntimeError("Discord rejected the credentials (401); check TOKEN/USER_AUTH in .env")
            if response.status_code == 403:
                raise RuntimeError("Discord denied message search (403); check history/content permissions")
            if response.status_code == 404:
                raise RuntimeError(f"Discord could not find guild {guild_id} (404)")
            response.raise_for_status()
            if not isinstance(payload, dict):
                raise RuntimeError("Discord returned an unexpected message-search response")
            return payload

        raise RuntimeError("Discord message search failed after retries")

    def download(
        self, candidate: MediaCandidate, output_dir: Path, media_id: str, force: bool
    ) -> DownloadedMedia | None:
        try:
            response = self.session.get(candidate.url, stream=True, timeout=(15, 120), allow_redirects=True)
        except requests.RequestException as error:
            print(f"    {candidate.label}: request failed ({type(error).__name__})")
            return None

        if response.status_code < 200 or response.status_code >= 300:
            print(f"    {candidate.label}: HTTP {response.status_code}")
            response.close()
            return None

        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_DOWNLOAD_BYTES:
            print(f"    {candidate.label}: response is larger than the 512 MiB safety limit")
            response.close()
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        total_size = 0
        first_bytes = b""
        download_complete = False

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{media_id}.", suffix=".part", dir=output_dir, delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    if not first_bytes:
                        first_bytes = chunk[:128]
                    total_size += len(chunk)
                    if total_size > MAX_DOWNLOAD_BYTES:
                        print(f"    {candidate.label}: response is larger than the 512 MiB safety limit")
                        return None
                    temporary_file.write(chunk)
                download_complete = True
        except requests.RequestException as error:
            print(f"    {candidate.label}: download failed ({type(error).__name__})")
            return None
        finally:
            response.close()
            if temporary_path and temporary_path.exists() and not download_complete:
                temporary_path.unlink(missing_ok=True)

        if is_imgur_deleted_placeholder(content_type, first_bytes, total_size):
            print(
                f"    {candidate.label}: Imgur returned its unavailable-item placeholder "
                f"({total_size} bytes, {IMGUR_DELETED_PLACEHOLDER_DIMENSIONS[0]}x"
                f"{IMGUR_DELETED_PLACEHOLDER_DIMENSIONS[1]} PNG)"
            )
            if temporary_path:
                temporary_path.unlink(missing_ok=True)
            return None

        extension = detect_extension(content_type, first_bytes)
        if extension is None:
            print(f"    {candidate.label}: response was not recognized as media ({content_type or 'unknown type'})")
            if temporary_path:
                temporary_path.unlink(missing_ok=True)
            return None

        if temporary_path is None:
            return None
        destination = output_path(output_dir, media_id, extension, force)
        temporary_path.replace(destination)
        return DownloadedMedia(path=destination, content_type=content_type or extension, size=total_size)


class ImgurUploadError(RuntimeError):
    """An upload failed before Imgur confirmed a new media item."""


class ImgurUploadUnknownError(RuntimeError):
    """The upload outcome is ambiguous; retrying could create a duplicate."""


class ImgurRateLimitError(ImgurUploadError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def parse_retry_after(response: requests.Response) -> float | None:
    header_value = response.headers.get("Retry-After")
    if header_value:
        try:
            return max(float(header_value), 0.0)
        except ValueError:
            pass

    try:
        payload = response.json()
    except ValueError:
        return None
    retry_after = payload.get("data", {}).get("retry_after") if isinstance(payload, dict) else None
    try:
        return max(float(retry_after), 0.0) if retry_after is not None else None
    except (TypeError, ValueError):
        return None


class ImgurClient:
    def __init__(self, client_id: str, min_upload_interval: float = 2.0, max_uploads_per_hour: int = 40):
        if not client_id.strip():
            raise ValueError("IMGUR_CLIENT_ID is empty")
        if max_uploads_per_hour < 1:
            raise ValueError("max_uploads_per_hour must be at least 1")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Client-ID {client_id.strip()}",
                "User-Agent": "tsuki-bot-content-recovery/1.0",
            }
        )
        self.min_upload_interval = max(min_upload_interval, 0.0)
        self.max_uploads_per_hour = max_uploads_per_hour
        self.last_upload_at: float | None = None
        self.upload_times: deque[float] = deque()
        self.last_rate_limits: dict[str, int | None] = {}

    def _wait_for_upload_slot(self) -> None:
        now = time.monotonic()
        while self.upload_times and now - self.upload_times[0] >= 3600:
            self.upload_times.popleft()

        if len(self.upload_times) >= self.max_uploads_per_hour:
            wait_seconds = 3600 - (now - self.upload_times[0])
            raise ImgurRateLimitError(
                f"Local Imgur upload budget reached ({self.max_uploads_per_hour}/hour)",
                wait_seconds,
            )

        if self.last_upload_at is not None:
            wait_seconds = self.min_upload_interval - (now - self.last_upload_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)

    def _capture_rate_limits(self, response: requests.Response) -> None:
        def integer_header(name: str) -> int | None:
            value = response.headers.get(name)
            try:
                return int(value) if value is not None else None
            except ValueError:
                return None

        self.last_rate_limits = {
            "user_remaining": integer_header("X-RateLimit-UserRemaining"),
            "client_remaining": integer_header("X-RateLimit-ClientRemaining"),
            "post_remaining": integer_header("X-Post-Rate-Limit-Remaining"),
        }

    def upload(self, input_path: Path) -> UploadedMedia:
        """Upload one file without automatically retrying an ambiguous POST."""

        if not input_path.is_file():
            raise ImgurUploadError(f"Upload input does not exist: {input_path}")

        mime_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
        self._wait_for_upload_slot()
        self.last_upload_at = time.monotonic()
        self.upload_times.append(self.last_upload_at)
        try:
            with input_path.open("rb") as input_file:
                response = self.session.post(
                    f"{IMGUR_API_BASE}/image",
                    files={"image": (input_path.name, input_file, mime_type)},
                    data={"type": "file"},
                    timeout=(15, 300),
                )
        except requests.Timeout as error:
            raise ImgurUploadUnknownError(
                "Imgur upload timed out; the server may have accepted it, so the POST will not be retried automatically"
            ) from error
        except requests.RequestException as error:
            raise ImgurUploadUnknownError(
                f"Imgur upload request failed ({type(error).__name__}); the server may have accepted it"
            ) from error

        self._capture_rate_limits(response)

        if response.status_code == 429:
            retry_after = parse_retry_after(response)
            raise ImgurRateLimitError(
                f"Imgur rate-limited the upload (429); retry_after={retry_after or 'unknown'}",
                retry_after,
            )
        if response.status_code < 200 or response.status_code >= 300:
            detail = response.text.strip()[:500]
            raise ImgurUploadError(f"Imgur upload failed with HTTP {response.status_code}: {detail}")

        try:
            payload = response.json()
        except ValueError as error:
            raise ImgurUploadError("Imgur returned a non-JSON upload response") from error

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ImgurUploadError("Imgur upload response did not contain a data object")

        media_id = data.get("id")
        link = data.get("mp4") or data.get("link")
        if not isinstance(media_id, str) or not media_id:
            raise ImgurUploadError("Imgur upload response did not contain a media ID")
        if not isinstance(link, str) or not link:
            raise ImgurUploadError("Imgur upload response did not contain a direct media URL")

        processing = data.get("processing")
        processing_status = processing.get("status") if isinstance(processing, dict) else None
        deletehash = data.get("deletehash")
        return UploadedMedia(
            media_id=media_id,
            url=link,
            deletehash=deletehash if isinstance(deletehash, str) else None,
            processing_status=processing_status if isinstance(processing_status, str) else None,
        )

    def verify_direct_url(self, media_url: str, attempts: int = 5) -> None:
        """Confirm that the returned direct URL is serving media before DB mutation."""

        for attempt in range(attempts):
            try:
                response = self.session.get(media_url, stream=True, timeout=(15, 60), allow_redirects=True)
            except requests.RequestException as error:
                if attempt == attempts - 1:
                    raise ImgurUploadError(f"Could not verify uploaded media URL: {error}") from error
                time.sleep(min(2**attempt, 10))
                continue

            try:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                first_bytes = next(response.iter_content(chunk_size=128), b"")
                if 200 <= response.status_code < 300 and detect_extension(content_type, first_bytes):
                    return
            finally:
                response.close()

            if attempt < attempts - 1:
                time.sleep(min(2**attempt, 10))

        raise ImgurUploadError(f"Imgur returned a URL that did not serve downloadable media: {media_url}")


def embed_source_strings(embed: dict) -> Iterable[str]:
    for key in ("url", "description", "title"):
        value = embed.get(key)
        if isinstance(value, str):
            yield value
    for key in ("video", "image", "thumbnail"):
        media = embed.get(key)
        if isinstance(media, dict) and isinstance(media.get("url"), str):
            yield media["url"]


def source_strings(message: dict) -> Iterable[str]:
    content = message.get("content")
    if isinstance(content, str):
        yield content

    for embed in message.get("embeds", []):
        if not isinstance(embed, dict):
            continue
        yield from embed_source_strings(embed)

    for attachment in message.get("attachments", []):
        if not isinstance(attachment, dict):
            continue
        for key in ("url", "filename", "description"):
            value = attachment.get(key)
            if isinstance(value, str):
                yield value


def message_matches(message: dict, target_url: str) -> bool:
    """Match the full submitted URL, rather than only its Imgur ID."""

    forms = search_url_forms(target_url)
    return any(form in value for form in forms for value in source_strings(message))


def embed_matches_target(embed: dict, target_url: str, media_id: str) -> bool:
    """Choose the embed for the requested URL inside a multi-embed message."""

    forms = search_url_forms(target_url)
    values = tuple(embed_source_strings(embed))
    return any(form in value for form in forms for value in values) or any(media_id in value for value in values)


def direct_imgur_candidates(media_id: str) -> Iterable[MediaCandidate]:
    for extension in (".mp4", ".webm", ".gif", ".jpg", ".png", ".jpeg", ".webp"):
        yield MediaCandidate(url=f"https://i.imgur.com/{media_id}{extension}", label=f"imgur{extension}")


def recover_direct_imgur(
    media_client: DiscordClient, media_id: str, output_dir: Path, force: bool
) -> DownloadedMedia | None:
    """Try Imgur's CDN directly before consulting Discord."""

    print(f"Trying direct Imgur recovery for {media_id}")
    for candidate in direct_imgur_candidates(media_id):
        print(f"  Trying {candidate.label}")
        downloaded = media_client.download(candidate, output_dir, media_id, force)
        if downloaded:
            print(f"Recovered {downloaded.size:,} bytes as {downloaded.content_type} via direct Imgur GET")
            return DownloadedMedia(
                path=downloaded.path,
                content_type=downloaded.content_type,
                size=downloaded.size,
                recovery_method="direct_imgur",
            )
    return None


def build_candidates(message: dict, target_url: str, media_id: str) -> list[MediaCandidate]:
    candidates: list[MediaCandidate] = []
    seen: set[str] = set()

    def add(url: object, label: str) -> None:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")) or url in seen:
            return
        seen.add(url)
        candidates.append(MediaCandidate(url=url, label=label))

    embeds = [
        embed
        for embed in message.get("embeds", [])
        if isinstance(embed, dict) and embed_matches_target(embed, target_url, media_id)
    ]
    for embed_index, embed in enumerate(embeds):
        if not isinstance(embed, dict):
            continue
        prefix = f"embed {embed_index + 1}"

        video = embed.get("video")
        if isinstance(video, dict):
            add(video.get("proxy_url"), f"{prefix} video proxy")
            add(video.get("url"), f"{prefix} video source")

        image = embed.get("image")
        if isinstance(image, dict):
            add(image.get("proxy_url"), f"{prefix} image proxy")
            add(image.get("url"), f"{prefix} image source")

        thumbnail = embed.get("thumbnail")
        if isinstance(thumbnail, dict):
            add(thumbnail.get("proxy_url"), f"{prefix} thumbnail proxy")
            add(thumbnail.get("url"), f"{prefix} thumbnail source")

        embed_url = embed.get("url")
        if isinstance(embed_url, str) and media_id in embed_url:
            if urlparse(embed_url).path.lower().endswith(MEDIA_EXTENSIONS):
                add(embed_url, f"{prefix} embed source")
        for candidate in direct_imgur_candidates(media_id):
            add(candidate.url, f"{prefix} {candidate.label}")

    for attachment_index, attachment in enumerate(message.get("attachments", [])):
        if not isinstance(attachment, dict):
            continue
        prefix = f"attachment {attachment_index + 1}"
        # The source URL is normally the original file; the proxy is useful if
        # the signed source URL has expired or the file was transformed.
        add(attachment.get("url"), f"{prefix} source")
        add(attachment.get("proxy_url"), f"{prefix} proxy")

    # A message may contain the URL but have no usable embed object anymore.
    # Try the conventional Imgur media URLs as a final fallback.
    if not candidates:
        candidates.extend(direct_imgur_candidates(media_id))
    return candidates


def detect_extension(content_type: str, first_bytes: bytes) -> str | None:
    """Validate a response and return a safe output extension."""

    if content_type.startswith(("text/", "application/json", "application/xml")):
        return None
    if b"ftyp" in first_bytes[:64]:
        return ".mp4"
    if first_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    if first_bytes.startswith(b"GIF8"):
        return ".gif"
    if first_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if first_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if first_bytes.startswith(b"RIFF") and b"WEBP" in first_bytes[:16]:
        return ".webp"

    mime_extensions = {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mime_extensions.get(content_type)


def png_dimensions(first_bytes: bytes) -> tuple[int, int] | None:
    """Read PNG dimensions from the header without adding an image dependency."""

    if len(first_bytes) < 24 or not first_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return struct.unpack(">II", first_bytes[16:24])


def is_imgur_deleted_placeholder(content_type: str, first_bytes: bytes, size: int) -> bool:
    """Recognize Imgur's small unavailable-item placeholder returned by old URLs."""

    return (
        content_type == "image/png"
        and size == IMGUR_DELETED_PLACEHOLDER_SIZE
        and png_dimensions(first_bytes) == IMGUR_DELETED_PLACEHOLDER_DIMENSIONS
    )


def output_path(output_dir: Path, media_id: str, extension: str, force: bool) -> Path:
    destination = output_dir / f"{media_id}{extension}"
    if force or not destination.exists():
        return destination

    counter = 2
    while True:
        candidate = output_dir / f"{media_id}-{counter}{extension}"
        if not candidate.exists():
            return candidate
        counter += 1


def recover_from_messages(
    media_client: DiscordClient,
    messages: Iterable[dict],
    target_url: str,
    media_id: str,
    output_dir: Path,
    force: bool,
) -> tuple[DownloadedMedia | None, int]:
    matches = 0
    for message in messages:
        if not message_matches(message, target_url):
            continue

        matches += 1
        message_id = message.get("id", "unknown")
        timestamp = message.get("timestamp", "unknown time")
        candidates = build_candidates(message, target_url, media_id)
        print(f"Found matching message {message_id} ({timestamp}); trying {len(candidates)} media URL(s)")
        for candidate in candidates:
            print(f"  Trying {candidate.label}")
            downloaded = media_client.download(candidate, output_dir, media_id, force)
            if downloaded:
                print(f"Recovered {downloaded.size:,} bytes as {downloaded.content_type}")
                print(f"Message: {message_id}")
                return (
                    DownloadedMedia(
                        path=downloaded.path,
                        content_type=downloaded.content_type,
                        size=downloaded.size,
                        recovery_method="discord",
                    ),
                    matches,
                )
    return None, matches


def history_search_and_recover(
    discord_client: DiscordClient,
    media_client: DiscordClient,
    channel_id: str,
    target_url: str,
    media_id: str,
    output_dir: Path,
    max_pages: int | None,
    force: bool,
) -> DownloadedMedia:
    before: str | None = None
    pages = 0
    scanned = 0
    matches = 0

    while max_pages is None or pages < max_pages:
        messages = discord_client.get_messages(channel_id, before)
        pages += 1
        if not messages:
            break

        scanned += len(messages)
        downloaded, page_matches = recover_from_messages(
            media_client, messages, target_url, media_id, output_dir, force
        )
        matches += page_matches
        if downloaded:
            return downloaded

        oldest_message_id = messages[-1].get("id")
        if not oldest_message_id or oldest_message_id == before:
            break
        before = str(oldest_message_id)
        print(f"Scanned {scanned:,} messages across {pages} page(s); matching messages: {matches}")

    if matches:
        raise RuntimeError("Found the original message, but none of its media URLs are still downloadable")
    raise RuntimeError(f"No message containing the exact URL {target_url!r} was found in the searched history")


def search_response_messages(response: dict) -> list[dict]:
    """Flatten Discord's nested search-result arrays into message objects."""

    flattened: list[dict] = []
    for group in response.get("messages", []):
        if isinstance(group, list):
            flattened.extend(message for message in group if isinstance(message, dict))
        elif isinstance(group, dict):
            flattened.append(group)
    return flattened


def recover_via_discord(
    discord_client: DiscordClient,
    media_client: DiscordClient,
    guild_id: str,
    channel_id: str,
    target_url: str,
    media_id: str,
    output_dir: Path,
    max_pages: int | None,
    force: bool,
    history_fallback: bool,
) -> DownloadedMedia:
    response = discord_client.search_messages(guild_id, channel_id, target_url)
    messages = search_response_messages(response)
    print(
        f"Indexed search returned {len(messages)} message result(s); total_results={response.get('total_results', 0)}"
    )

    downloaded, matches = recover_from_messages(media_client, messages, target_url, media_id, output_dir, force)
    if downloaded:
        return downloaded
    if matches:
        raise RuntimeError("Found the original message, but none of its media URLs are still downloadable")

    if history_fallback:
        print("No indexed match; falling back to channel-history pagination")
        return history_search_and_recover(
            discord_client, media_client, channel_id, target_url, media_id, output_dir, max_pages, force
        )

    raise RuntimeError(
        f"Discord's indexed search found no message containing the exact URL {target_url!r}; "
        "retry with --history-fallback if needed"
    )


def recover_content(
    media_client: DiscordClient,
    auth_env: str | None,
    guild_id: str,
    channel_id: str,
    target_url: str,
    media_id: str,
    output_dir: Path,
    max_pages: int | None,
    force: bool,
    history_fallback: bool,
) -> DownloadedMedia:
    """Run recovery methods in order, with Discord as the backup method."""

    if downloaded := recover_direct_imgur(media_client, media_id, output_dir, force):
        return downloaded

    print("Direct Imgur recovery failed; trying Discord backup")
    authorization, auth_source = auth_header(auth_env)
    print(f"Searching channel {channel_id} for URL {target_url} using {auth_source}")
    if auth_source == "USER_AUTH":
        print("Warning: USER_AUTH is being used; prefer a bot TOKEN with channel history permissions.")

    discord_client = DiscordClient(authorization)
    return recover_via_discord(
        discord_client,
        media_client,
        guild_id,
        channel_id,
        target_url,
        media_id,
        output_dir,
        max_pages,
        force,
        history_fallback,
    )


def run_single_cli(argv: list[str] | None = None) -> int:
    """Run recovery for one URL without retaining media files locally."""

    args = parse_single_args(argv)
    load_dotenv(REPO_ROOT / ".env")

    try:
        media_id = extract_imgur_id(args.url)
        target_url = args.url.strip()
        channel_id = str(args.channel_id)
        guild_id = str(args.guild_id)
        if not channel_id.isdigit() or not guild_id.isdigit():
            raise ValueError("guild and channel IDs must contain only digits")
        if args.dump_search:
            authorization, auth_source = auth_header(args.auth_env)
            print(f"Searching channel {channel_id} for URL {target_url} using {auth_source}")
            if auth_source == "USER_AUTH":
                print("Warning: USER_AUTH is being used; prefer a bot TOKEN with channel history permissions.")
            response = DiscordClient(authorization).search_messages(args.guild_id, channel_id, target_url)
            print(json.dumps(response, indent=2, ensure_ascii=False))
            return 0
        with tempfile.TemporaryDirectory(prefix="content-recovery-") as temporary_dir:
            downloaded = recover_content(
                DiscordClient(),
                args.auth_env,
                guild_id,
                channel_id,
                target_url,
                media_id,
                Path(temporary_dir),
                args.max_pages,
                args.force,
                args.history_fallback,
            )
            trim_first_frame(downloaded.path, args.force)
        print("Trimmed first frame; temporary recovery files were removed.")
        return 0
    except (ValueError, RuntimeError, requests.RequestException) as error:
        print(f"Recovery failed: {error}", file=sys.stderr)
        return 1


@dataclass(frozen=True)
class Candidate:
    """A reported Imgur link selected for the recovery pipeline."""

    content_link_id: int
    role_id: str
    url: str
    num_reports: int
    initial_reaction_count: int
    author: str | None
    uploaded_date: str | None


@dataclass(frozen=True)
class RecoveryBatchConfig:
    """Configuration for a single database-backed recovery batch."""

    role_id: str | None = None
    limit: int = 50
    threshold: int = 5
    guild_id: str = DEFAULT_GUILD_ID
    channel_id: str = DEFAULT_CHANNEL_ID
    auth_env: str | None = None
    max_pages: int | None = None
    history_fallback: bool = False
    imgur_client_id_env: str = "IMGUR_CLIENT_ID"
    upload_interval: float = 2.0
    max_uploads_per_hour: int = 50


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not loaded; fix .env or provide it in the process environment")
    return database_url


def fetch_candidates(
    connection: psycopg.Connection[Any], role_id: str | None, threshold: int, limit: int
) -> list[Candidate]:
    """Select reported Imgur URLs in the order with the most user impact first."""

    if limit < 1:
        raise ValueError("--limit must be at least 1")
    if threshold < 1:
        raise ValueError("--threshold must be at least 1")
    if role_id and not role_id.isdigit():
        raise ValueError("--role-id must contain only digits")

    role_filter = ""
    params: list[object] = [threshold]
    if role_id:
        role_filter = "AND role_id = %s"
        params.append(role_id)
    params.append(limit)

    query = f"""
        SELECT
            content_link_id,
            role_id,
            url,
            num_reports,
            COALESCE(initial_reaction_count, 0) AS initial_reaction_count,
            author,
            uploaded_date
        FROM content_links
        WHERE num_reports >= %s
          AND url ILIKE '%%imgur.com/%%'
          {role_filter}
        ORDER BY initial_reaction_count DESC, num_reports DESC, uploaded_date ASC, content_link_id ASC
        LIMIT %s
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [
        Candidate(
            content_link_id=int(row["content_link_id"]),
            role_id=str(row["role_id"]),
            url=str(row["url"]),
            num_reports=int(row["num_reports"]),
            initial_reaction_count=int(row["initial_reaction_count"]),
            author=row["author"],
            uploaded_date=str(row["uploaded_date"]) if row["uploaded_date"] is not None else None,
        )
        for row in rows
    ]


def start_recovery_item(connection: psycopg.Connection[Any], batch_id: str, candidate: Candidate) -> None:
    """Create the audit row only when the candidate is actually started."""

    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO content_link_recovery_items
                    (batch_id, content_link_id, original_url, num_reports_before, status, started_at)
                VALUES (%s, %s, %s, %s, 'running', NOW());
                """,
                (batch_id, candidate.content_link_id, candidate.url, candidate.num_reports),
            )


def update_recovery_item(
    connection: psycopg.Connection[Any],
    batch_id: str,
    candidate: Candidate,
    status: str,
    *,
    replacement_url: str | None = None,
    recovery_method: str | None = None,
    imgur_id: str | None = None,
    downloaded_size: int | None = None,
    trimmed_size: int | None = None,
    trimmed_sha256: str | None = None,
    error: str | None = None,
    num_reports_after: int | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE content_link_recovery_items
            SET status = %s,
                replacement_url = %s,
                recovery_method = %s,
                imgur_id = %s,
                downloaded_size = %s,
                trimmed_size = %s,
                trimmed_sha256 = %s,
                error = %s,
                num_reports_after = %s,
                finished_at = NOW()
            WHERE batch_id = %s AND content_link_id = %s;
            """,
            (
                status,
                replacement_url,
                recovery_method,
                imgur_id,
                downloaded_size,
                trimmed_size,
                trimmed_sha256,
                error[:4000] if error else None,
                num_reports_after,
                batch_id,
                candidate.content_link_id,
            ),
        )
    connection.commit()


def summarize_recovery_batch(
    connection: psycopg.Connection[Any], batch_id: str, selected_count: int, stopped: bool, error: str | None
) -> dict[str, int | str | None]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'updated') AS succeeded_count,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
                COUNT(*) FILTER (WHERE status = 'rate_limited') AS rate_limited_count,
                COUNT(*) FILTER (WHERE status = 'upload_unknown') AS ambiguous_count,
                COUNT(*) FILTER (WHERE status IN ('pending', 'running')) AS skipped_count,
                COUNT(*) AS logged_count
            FROM content_link_recovery_items
            WHERE batch_id = %s;
            """,
            (batch_id,),
        )
        counts = dict(cursor.fetchone())
    logged_count = counts.pop("logged_count")
    counts["skipped_count"] += max(selected_count - logged_count, 0)
    has_unresolved = counts["skipped_count"] > 0
    has_errors = any(counts[key] > 0 for key in ("failed_count", "rate_limited_count", "ambiguous_count"))
    return {
        "batch_id": batch_id,
        "status": "partial" if stopped or has_unresolved or has_errors else "completed",
        "selected_count": selected_count,
        **counts,
        "error": error,
    }


def apply_success(
    connection: psycopg.Connection[Any],
    candidate: Candidate,
    replacement_url: str,
    batch_id: str,
    recovery_method: str | None,
    downloaded_size: int,
    trimmed_size: int,
    trimmed_sha256: str,
    imgur_id: str,
) -> None:
    """Atomically replace a link and mark its recovery audit item as complete."""

    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE content_links
                SET original_url = COALESCE(original_url, %s),
                    url = %s,
                    num_reports = 0,
                    processed_date = NOW()
                WHERE content_link_id = %s
                  AND url = %s
                  AND num_reports = %s;
                """,
                (candidate.url, replacement_url, candidate.content_link_id, candidate.url, candidate.num_reports),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Database row changed or disappeared for content_link_id={candidate.content_link_id}; "
                    "the uploaded URL was not recorded"
                )
            cursor.execute(
                """
                UPDATE content_link_recovery_items
                SET status = 'updated',
                    replacement_url = %s,
                    recovery_method = %s,
                    imgur_id = %s,
                    downloaded_size = %s,
                    trimmed_size = %s,
                    trimmed_sha256 = %s,
                    num_reports_after = 0,
                    finished_at = NOW(),
                    error = NULL
                WHERE batch_id = %s AND content_link_id = %s;
                """,
                (
                    replacement_url,
                    recovery_method,
                    imgur_id,
                    downloaded_size,
                    trimmed_size,
                    trimmed_sha256,
                    batch_id,
                    candidate.content_link_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Recovery audit row disappeared for batch_id={batch_id}, "
                    f"content_link_id={candidate.content_link_id}"
                )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def print_candidates(candidates: list[Candidate]) -> None:
    if not candidates:
        print("No Imgur candidates matched the selection.")
        return
    print("content_link_id  initial  reports  role_id             url")
    print("----------------  -------  -------  ------------------  ----------------------------------------")
    for candidate in candidates:
        print(
            f"{candidate.content_link_id:<16} {candidate.initial_reaction_count:<7} "
            f"{candidate.num_reports:<7}  {candidate.role_id:<18}  {candidate.url}"
        )


def process_candidate(
    connection: psycopg.Connection[Any],
    candidate: Candidate,
    config: RecoveryBatchConfig,
    media_client: DiscordClient,
    imgur_client: ImgurClient,
    batch_id: str,
) -> None:
    """Recover, trim, upload, and record a single candidate."""

    downloaded: DownloadedMedia | None = None
    trimmed: Path | None = None
    uploaded: UploadedMedia | None = None
    trimmed_sha256: str | None = None

    start_recovery_item(connection, batch_id, candidate)

    def mark_failure(status: str, error: str) -> None:
        update_recovery_item(
            connection,
            batch_id,
            candidate,
            status,
            replacement_url=uploaded.url if uploaded else None,
            recovery_method=downloaded.recovery_method if downloaded else None,
            imgur_id=uploaded.media_id if uploaded else None,
            downloaded_size=downloaded.size if downloaded else None,
            trimmed_size=trimmed.stat().st_size if trimmed and trimmed.exists() else None,
            trimmed_sha256=trimmed_sha256,
            error=error,
            num_reports_after=candidate.num_reports,
        )

    with tempfile.TemporaryDirectory(prefix=f"content-recovery-{candidate.content_link_id}-") as temporary_dir:
        row_output_dir = Path(temporary_dir)
        try:
            downloaded = recover_content(
                media_client,
                config.auth_env,
                config.guild_id,
                config.channel_id,
                candidate.url,
                extract_imgur_id(candidate.url),
                row_output_dir,
                config.max_pages,
                True,
                config.history_fallback,
            )
            trimmed = trim_first_frame(downloaded.path, True)
            trimmed_sha256 = sha256(trimmed)
            uploaded = imgur_client.upload(trimmed)
            imgur_client.verify_direct_url(uploaded.url)
            apply_success(
                connection,
                candidate,
                uploaded.url,
                batch_id,
                downloaded.recovery_method,
                downloaded.size,
                trimmed.stat().st_size,
                trimmed_sha256,
                uploaded.media_id,
            )
        except ImgurRateLimitError as error:
            mark_failure("rate_limited", str(error))
            raise
        except ImgurUploadUnknownError as error:
            mark_failure("upload_unknown", str(error))
            raise
        except Exception as error:
            mark_failure("failed", str(error))
            print(f"FAILED {candidate.content_link_id}: {error}")
            return

    print(f"UPDATED {candidate.content_link_id}: {candidate.url} -> {uploaded.url}")


def run_recovery_batch(config: RecoveryBatchConfig, *, print_candidates_output: bool = True) -> dict[str, object]:
    """Run one recovery batch and return its database-backed summary."""

    client_id = os.getenv(config.imgur_client_id_env, "").strip()
    if not client_id:
        raise RuntimeError(f"{config.imgur_client_id_env} is not loaded")

    with psycopg.connect(get_database_url()) as connection:
        candidates = fetch_candidates(connection, config.role_id, config.threshold, config.limit)
        connection.commit()
        if print_candidates_output:
            print_candidates(candidates)
        if not candidates:
            return {
                "batch_id": None,
                "status": "completed",
                "selected_count": 0,
                "succeeded_count": 0,
                "failed_count": 0,
                "rate_limited_count": 0,
                "ambiguous_count": 0,
                "skipped_count": 0,
                "error": None,
            }

        media_client = DiscordClient()
        imgur_client = ImgurClient(
            client_id,
            min_upload_interval=config.upload_interval,
            max_uploads_per_hour=config.max_uploads_per_hour,
        )
        batch_id = uuid.uuid4().hex
        stopped = False
        stop_reason = None
        try:
            for candidate in candidates:
                try:
                    process_candidate(connection, candidate, config, media_client, imgur_client, batch_id)
                except ImgurRateLimitError as error:
                    stopped = True
                    stop_reason = str(error)
                    print("Stopping the batch after an Imgur rate limit; no further uploads will be attempted.")
                    break
                except ImgurUploadUnknownError as error:
                    stopped = True
                    stop_reason = str(error)
                    print("Stopping the batch because an Imgur upload outcome was ambiguous.")
                    break
        finally:
            summary = summarize_recovery_batch(connection, batch_id, len(candidates), stopped, stop_reason)
            print(
                f"Batch {batch_id}: {summary['status']} | "
                f"succeeded={summary['succeeded_count']} "
                f"failed={summary['failed_count']} "
                f"rate_limited={summary['rate_limited_count']} "
                f"ambiguous={summary['ambiguous_count']} "
                f"skipped={summary['skipped_count']}"
            )
        return summary


def parse_batch_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover, transform, re-upload, and replace reported Imgur links.")
    parser.add_argument("--role-id", help="Only recover links for this role; omit to consider all roles")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of candidates to select (default: 50)")
    parser.add_argument("--threshold", type=int, default=5, help="Minimum num_reports to select (default: 5)")
    parser.add_argument(
        "--apply", action="store_true", help="Perform recovery and database updates; otherwise only print candidates"
    )
    parser.add_argument(
        "--channel-id", default=DEFAULT_CHANNEL_ID, help=f"Discord channel to search (default: {DEFAULT_CHANNEL_ID})"
    )
    parser.add_argument(
        "--guild-id",
        default=DEFAULT_GUILD_ID,
        help=f"Discord guild containing the channel (default: {DEFAULT_GUILD_ID})",
    )
    parser.add_argument(
        "--auth-env",
        choices=("TOKEN", "DISCORD_TOKEN", "USER_AUTH"),
        help="Environment variable containing Discord credentials",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None, help="With --history-fallback, stop after this many 100-message pages"
    )
    parser.add_argument(
        "--history-fallback", action="store_true", help="Fall back to channel history if indexed search finds nothing"
    )
    parser.add_argument(
        "--imgur-client-id-env",
        default="IMGUR_CLIENT_ID",
        help="Environment variable containing the Imgur client ID (default: IMGUR_CLIENT_ID)",
    )
    parser.add_argument(
        "--upload-interval", type=float, default=2.0, help="Minimum seconds between Imgur uploads (default: 2)"
    )
    parser.add_argument(
        "--max-uploads-per-hour", type=int, default=50, help="Conservative local upload budget (default: 50)"
    )
    return parser.parse_args(argv)


def run_batch_cli(argv: list[str] | None = None) -> int:
    """Run the command-line batch interface; dry-run unless ``--apply`` is set."""

    args = parse_batch_args(argv)
    load_dotenv(REPO_ROOT / ".env")
    try:
        config = RecoveryBatchConfig(
            role_id=args.role_id,
            limit=args.limit,
            threshold=args.threshold,
            guild_id=args.guild_id,
            channel_id=args.channel_id,
            auth_env=args.auth_env,
            max_pages=args.max_pages,
            history_fallback=args.history_fallback,
            imgur_client_id_env=args.imgur_client_id_env,
            upload_interval=args.upload_interval,
            max_uploads_per_hour=args.max_uploads_per_hour,
        )
        if not args.apply:
            with psycopg.connect(get_database_url()) as connection:
                candidates = fetch_candidates(connection, config.role_id, config.threshold, config.limit)
            print_candidates(candidates)
            print("Dry run only; pass --apply to recover, upload, and update rows.")
            return 0
        run_recovery_batch(config)
        return 0
    except (RuntimeError, ValueError, psycopg.Error) as error:
        print(f"Batch recovery failed: {error}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Dispatch either the single-URL recovery or batch recovery command."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "batch":
        return run_batch_cli(arguments[1:])
    return run_single_cli(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
