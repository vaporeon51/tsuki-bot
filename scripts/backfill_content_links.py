#!/usr/bin/env python3
"""Backfill role-less Discord media continuations through the live ingestion rules.

Defaults to a dry run. Apply table_updates23.sql before using --apply.
"""

import argparse
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from src import content_discord, content_ingestion


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Discord media continuations into content_links.")
    parser.add_argument(
        "--after-message-id",
        default="0",
        help="Start after this Discord message ID; 0 starts at the channel's earliest message.",
    )
    parser.add_argument(
        "--before-message-id",
        help="Stop once this Discord message ID has been processed (inclusive).",
    )
    parser.add_argument("--role-id", help="Only write links associated with this role ID.")
    parser.add_argument("--max-messages", type=int, help="Stop after this many messages; useful for trial runs.")
    parser.add_argument(
        "--show-candidates",
        action="store_true",
        help="Print each continuation candidate during a dry run or apply run.",
    )
    parser.add_argument("--apply", action="store_true", help="Insert missing links; otherwise only report candidates.")
    return parser.parse_args(argv)


def validate_message_id(value: str, flag: str) -> int:
    if not value.isdigit():
        raise ValueError(f"{flag} must contain only digits")
    return int(value)


def run_backfill(args: argparse.Namespace) -> int:
    after_id = validate_message_id(args.after_message_id, "--after-message-id")
    before_id = validate_message_id(args.before_message_id, "--before-message-id") if args.before_message_id else None
    if before_id is not None and before_id <= after_id:
        raise ValueError("--before-message-id must be greater than --after-message-id")
    if args.role_id and not args.role_id.isdigit():
        raise ValueError("--role-id must contain only digits")
    if args.max_messages is not None and args.max_messages < 1:
        raise ValueError("--max-messages must be at least 1")

    classifier = content_ingestion.ContentMessageClassifier()
    cursor = str(after_id)
    processed_date = datetime.now()
    processed_messages = 0
    candidate_count = 0
    inserted_count = 0
    kind_counts: Counter[str] = Counter()
    write_links: Callable[[datetime, list[content_ingestion.ContentLinkDraft]], int] | None = None
    if args.apply:
        from src.db import content_update as content_update_db

        write_links = content_update_db.insert_content_links

    print(
        f"Content-link backfill starting: after={after_id} "
        f"before={before_id if before_id is not None else 'end'} "
        f"role_id={args.role_id or 'all'} apply={args.apply}"
    )

    while True:
        page = content_discord.get_messages_after(cursor)
        if not page:
            break
        page.sort(key=lambda message: int(message["id"]))

        if before_id is not None:
            page = [message for message in page if int(message["id"]) <= before_id]
        if args.max_messages is not None:
            remaining = args.max_messages - processed_messages
            page = page[:remaining]
        if not page:
            break

        page_links = []
        for message in page:
            links = [link for link in classifier.consume(message) if link.source_kind != content_ingestion.ROOT]
            if args.role_id:
                links = [link for link in links if link.role_id == args.role_id]
            page_links.extend(links)
            kind_counts.update(link.source_kind for link in links)
            if args.show_candidates:
                for link in links:
                    print(
                        f"CANDIDATE kind={link.source_kind} message_id={link.source_message_id} "
                        f"root_message_id={link.root_message_id} role_id={link.role_id} url={link.url}"
                    )

        candidate_count += len(page_links)
        if write_links is not None:
            inserted_count += write_links(processed_date, page_links)

        processed_messages += len(page)
        cursor = str(page[-1]["id"])
        print(
            f"Processed {processed_messages:,} messages through {page[-1]['timestamp']}; "
            f"candidates={candidate_count:,} inserted={inserted_count:,}."
        )

        if (before_id is not None and int(cursor) >= before_id) or (
            args.max_messages is not None and processed_messages >= args.max_messages
        ):
            break
        time.sleep(content_discord.REQUEST_DELAY_SECONDS)

    kinds = " ".join(
        f"{kind}={kind_counts[kind]:,}"
        for kind in (content_ingestion.REPLY_CONTINUATION, content_ingestion.UNTHREADED_CONTINUATION)
    )
    print(
        f"Content-link backfill finished: processed_messages={processed_messages:,} "
        f"candidates={candidate_count:,} inserted={inserted_count:,} {kinds or 'no matching media'}"
    )
    if not args.apply:
        print("Dry run only; apply table_updates23.sql, then pass --apply to insert missing links.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run_backfill(parse_args(argv))
    except (RuntimeError, ValueError) as error:
        print(f"Content-link backfill failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
