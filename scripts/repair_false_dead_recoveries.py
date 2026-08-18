#!/usr/bin/env python3
"""Apply recovery uploads that Discord eventually verified as live.

Before the delayed-unfurl fix, recovery verification could record an uploaded
replacement as dead before Discord generated its embed. This script scans the
recovery verification channel from the known affected message forward and
applies only replacement URLs that now have Discord's ``gifv`` embed.

Usage:
    python scripts/repair_false_dead_recoveries.py
    python scripts/repair_false_dead_recoveries.py --apply
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import psycopg
from dotenv import load_dotenv

from repair_false_dead_links import REPO_ROOT, get_messages_from


DEFAULT_CHANNEL_ID = "1536908360673271918"
DEFAULT_START_MESSAGE_ID = "1537836536173826178"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID, help="Recovery verification channel ID")
    parser.add_argument(
        "--start-message-id",
        default=DEFAULT_START_MESSAGE_ID,
        help="First affected recovery verification message ID (inclusive)",
    )
    parser.add_argument("--apply", action="store_true", help="Persist repairs; default is a dry run")
    return parser.parse_args()


def live_replacement_urls(messages: Iterable[dict[str, Any]]) -> set[str]:
    """Return uploaded URLs whose retained recovery probe now has a ``gifv`` embed."""

    return {
        content
        for message in messages
        if isinstance((content := message.get("content")), str)
        and content.startswith("https://i.imgur.com/")
        and any(
            isinstance(embed, dict) and embed.get("type") == "gifv"
            for embed in message.get("embeds", [])
        )
    }


def repair_recoveries(
    connection: psycopg.Connection[Any],
    replacement_urls: set[str],
    started_at: datetime,
    apply: bool,
) -> tuple[int, int]:
    """Return the number of corrected recovery items and content-link rows."""

    if not replacement_urls:
        return 0, 0

    params = (started_at, sorted(replacement_urls))
    selected = """
        WITH selected AS (
            SELECT DISTINCT ON (link.url)
                item.ctid AS item_ctid,
                item.original_url,
                item.replacement_url,
                item.replacement_generation,
                link.url AS source_url
            FROM content_link_recovery_items AS item
            JOIN content_links AS link ON link.content_link_id = item.content_link_id
            WHERE item.status = 'dead'
              AND item.started_at >= %s
              AND item.replacement_url = ANY(%s::TEXT[])
              AND link.is_dead = TRUE
              AND link.recovery_generation = item.replacement_generation
            ORDER BY link.url, item.finished_at DESC NULLS LAST, item.started_at DESC, item.ctid DESC
        )
    """
    with connection.cursor() as cursor:
        if not apply:
            cursor.execute(
                selected
                + """
                SELECT
                    COUNT(*) AS recovery_items,
                    COALESCE(
                        SUM((SELECT COUNT(*) FROM content_links WHERE url = selected.source_url AND is_dead = TRUE)),
                        0
                    ) AS content_links
                FROM selected;
                """,
                params,
            )
            recovery_items, content_links = cursor.fetchone()
            return int(recovery_items), int(content_links)

        cursor.execute(
            selected
            + """
            , updated_links AS (
                UPDATE content_links AS link
                SET original_url = COALESCE(link.original_url, selected.original_url),
                    url = selected.replacement_url,
                    recovery_generation = selected.replacement_generation,
                    is_dead = FALSE,
                    is_recovery_exhausted = FALSE,
                    processed_date = NOW()
                FROM selected
                WHERE link.url = selected.source_url
                  AND link.is_dead = TRUE
                RETURNING link.content_link_id
            ), updated_items AS (
                UPDATE content_link_recovery_items AS item
                SET status = 'updated',
                    error = NULL
                FROM selected
                WHERE item.ctid = selected.item_ctid
                RETURNING item.ctid
            )
            SELECT
                (SELECT COUNT(*) FROM updated_items) AS recovery_items,
                (SELECT COUNT(*) FROM updated_links) AS content_links;
            """,
            params,
        )
        recovery_items, content_links = cursor.fetchone()
        return int(recovery_items), int(content_links)


def main() -> int:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    if not args.channel_id.isdigit() or not args.start_message_id.isdigit():
        raise ValueError("channel and message IDs must contain only digits")

    messages = get_messages_from(args.channel_id, args.start_message_id)
    replacement_urls = live_replacement_urls(messages)
    started_at = datetime.fromisoformat(messages[0]["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)
    print(f"Scanned {len(messages)} retained messages and found {len(replacement_urls)} live recovery uploads.")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not loaded; fix .env or provide it in the process environment")
    with psycopg.connect(database_url) as connection:
        recovery_items, content_links = repair_recoveries(connection, replacement_urls, started_at, args.apply)

    verb = "Corrected" if args.apply else "Dry run:"
    suffix = "" if args.apply else " would be corrected"
    print(f"{verb} {recovery_items} recovery audit items and {content_links} content-link rows{suffix}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
