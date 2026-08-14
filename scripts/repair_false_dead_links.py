#!/usr/bin/env python3
"""Restore links incorrectly marked dead before Discord finished unfurling.

The dead-link checker briefly treated a message with no embed as a broken Imgur
link. This script scans its private probe channel from a known affected message
forward, finds dead-link notices whose corresponding probe now has a ``gifv``
embed, and restores only those database rows.

Usage:
    python scripts/repair_false_dead_links.py
    python scripts/repair_false_dead_links.py --apply
"""

from __future__ import annotations

import argparse
import os
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
DISCORD_API_BASE = "https://discord.com/api/v10"
DEFAULT_CHANNEL_ID = "1537540189595901952"
DEFAULT_START_MESSAGE_ID = "1537836635713183796"
DEAD_LINK_NOTICE = re.compile(r"^⚠️ Dead link detected: <(?P<url>https://i\.imgur\.com/[^>]+)>")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID, help="Dead-link checker channel ID")
    parser.add_argument(
        "--start-message-id",
        default=DEFAULT_START_MESSAGE_ID,
        help="First affected probe message ID (inclusive)",
    )
    parser.add_argument("--apply", action="store_true", help="Persist the repairs; default is a dry run")
    return parser.parse_args()


def discord_headers() -> dict[str, str]:
    token = os.getenv("TOKEN", "").strip()
    if not token:
        raise RuntimeError("TOKEN is not loaded; fix .env or provide it in the process environment")
    return {"Authorization": token if token.lower().startswith("bot ") else f"Bot {token}"}


def get_messages_from(channel_id: str, start_message_id: str) -> list[dict[str, Any]]:
    """Fetch every currently retained channel message from the start ID onward."""

    headers = discord_headers()
    endpoint = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    response = requests.get(f"{endpoint}/{start_message_id}", headers=headers, timeout=30)
    response.raise_for_status()
    messages = [response.json()]
    after = start_message_id

    while True:
        response = requests.get(endpoint, params={"after": after, "limit": 100}, headers=headers, timeout=30)
        if response.status_code == 429:
            retry_after = float(response.json().get("retry_after", 1))
            time.sleep(retry_after)
            continue
        response.raise_for_status()
        page = response.json()
        if not page:
            return messages
        messages.extend(page)
        after = max(message["id"] for message in page)


def urls_to_restore(messages: Iterable[dict[str, Any]]) -> set[str]:
    """Return notified URLs whose retained probe has Discord's live ``gifv`` embed."""

    probe_embed_types: dict[str, set[str]] = {}
    notified_urls: set[str] = set()
    for message in messages:
        content = message.get("content", "")
        notice_match = DEAD_LINK_NOTICE.match(content)
        if notice_match:
            notified_urls.add(notice_match.group("url"))
            continue

        if not isinstance(content, str) or not content.startswith("https://i.imgur.com/"):
            continue
        embed_types = {
            embed.get("type")
            for embed in message.get("embeds", [])
            if isinstance(embed, dict) and isinstance(embed.get("type"), str)
        }
        if embed_types:
            probe_embed_types.setdefault(content, set()).update(embed_types)

    return {
        url
        for url in notified_urls
        if "gifv" in probe_embed_types.get(url, set())
    }


def restore_urls(connection: psycopg.Connection[Any], urls: set[str], apply: bool) -> tuple[int, int]:
    """Return (matching dead rows, restored rows), updating only when requested."""

    if not urls:
        return 0, 0

    ordered_urls = sorted(urls)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM content_links WHERE is_dead = TRUE AND url = ANY(%s::TEXT[]);",
            (ordered_urls,),
        )
        matching_rows = int(cursor.fetchone()[0])
        if not apply:
            return matching_rows, 0

        cursor.execute(
            """
            UPDATE content_links
            SET is_dead = FALSE,
                is_recovery_exhausted = FALSE
            WHERE is_dead = TRUE
              AND url = ANY(%s::TEXT[]);
            """,
            (ordered_urls,),
        )
        return matching_rows, cursor.rowcount


def main() -> int:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    if not args.channel_id.isdigit() or not args.start_message_id.isdigit():
        raise ValueError("channel and message IDs must contain only digits")

    messages = get_messages_from(args.channel_id, args.start_message_id)
    urls = urls_to_restore(messages)
    print(f"Scanned {len(messages)} retained messages and found {len(urls)} confirmed false-positive URLs.")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not loaded; fix .env or provide it in the process environment")
    with psycopg.connect(database_url) as connection:
        matching_rows, restored_rows = restore_urls(connection, urls, args.apply)

    if args.apply:
        print(f"Restored {restored_rows} of {matching_rows} currently dead content_links rows.")
    else:
        print(f"Dry run: {matching_rows} currently dead content_links rows would be restored. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
