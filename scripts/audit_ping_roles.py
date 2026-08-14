"""Compare role mentions in a Discord ping-role channel with ``role_info``.

The command is read-only: it only lists IDs that need attention and never
inserts, updates, or deletes database rows.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_GUILD_ID = "124767749099618304"
DEFAULT_CHANNEL_ID = "779827588180869152"
ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
ROLE_LIST_ENTRY_RE = re.compile(r"^.+?\s+(\d{17,20})\s*$", re.MULTILINE)
PING_ROLE_LIST_HEADER = "available ping roles"


@dataclass(frozen=True)
class RoleInfo:
    role_id: str
    string_tag: str | None
    member_name: str | None
    group_name: str | None

    @property
    def label(self) -> str:
        return self.string_tag or "(no string_tag)"


@dataclass(frozen=True)
class PingRoleAudit:
    found_role_ids: frozenset[str]
    new_role_ids: frozenset[str]
    missing_role_ids: frozenset[str]
    message_ids_by_role_id: dict[str, tuple[str, ...]]
    scanned_message_count: int
    scanned_page_count: int


def strings_in_payload(value: object) -> Iterable[str]:
    """Yield strings from nested Discord message fields such as embeds."""

    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings_in_payload(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings_in_payload(child)


def role_ids_in_message(message: dict[str, Any]) -> set[str]:
    """Return role IDs mentioned in a Discord API message payload.

    ``mention_roles`` is the canonical API field.  The textual fallback covers
    messages whose structured mention field was omitted by Discord.
    """

    raw_role_ids = message.get("mention_roles", [])
    if not isinstance(raw_role_ids, list):
        raw_role_ids = []
    role_ids = {str(role_id) for role_id in raw_role_ids if isinstance(role_id, (str, int)) and str(role_id).isdigit()}
    for text in strings_in_payload(message):
        role_ids.update(ROLE_MENTION_RE.findall(text))
    return role_ids


def role_ids_in_ping_role_listing(message: dict[str, Any]) -> set[str]:
    """Read IDs from one current ping-role roster message.

    The roster channel stores each role as plain text in the form
    ``Role name 123456789012345678``, rather than as a Discord mention.
    """

    role_ids = role_ids_in_message(message)
    content = message.get("content", "")
    if isinstance(content, str):
        role_ids.update(ROLE_LIST_ENTRY_RE.findall(content))
    return role_ids


def collect_ping_role_ids(
    fetch_page: Callable[[str | None], list[dict[str, Any]]],
    max_pages: int,
    delay_seconds: float = 0.0,
) -> tuple[dict[str, tuple[str, ...]], int, int]:
    """Walk newest-to-oldest message pages and retain mention provenance."""

    all_messages: list[dict[str, Any]] = []
    before_message_id: str | None = None
    scanned_messages = 0
    scanned_pages = 0

    for page_number in range(max_pages):
        messages = fetch_page(before_message_id)
        if not messages:
            break

        scanned_pages += 1
        scanned_messages += len(messages)
        all_messages.extend(messages)

        valid_message_ids = (
            str(message["id"])
            for message in messages
            if isinstance(message.get("id"), (str, int)) and str(message["id"]).isdigit()
        )
        oldest_message_id = min(
            valid_message_ids,
            key=int,
            default=None,
        )
        if oldest_message_id is None or oldest_message_id == before_message_id or len(messages) < 100:
            break
        before_message_id = oldest_message_id
        if page_number + 1 < max_pages and delay_seconds:
            time.sleep(delay_seconds)

    seen_message_ids_by_role_id: dict[str, list[str]] = defaultdict(list)
    reading_current_roster = False
    for message in sorted(all_messages, key=lambda item: int(str(item.get("id", "0")))):
        content = message.get("content", "")
        normalized_content = content.casefold() if isinstance(content, str) else ""
        if PING_ROLE_LIST_HEADER in normalized_content:
            reading_current_roster = True
            continue
        if reading_current_roster and "old roles" in normalized_content:
            reading_current_roster = False
            continue
        if not reading_current_roster:
            continue

        message_id = message.get("id")
        if not isinstance(message_id, (str, int)):
            continue
        for role_id in role_ids_in_ping_role_listing(message):
            seen_message_ids_by_role_id[role_id].append(str(message_id))

    return (
        {role_id: tuple(message_ids) for role_id, message_ids in seen_message_ids_by_role_id.items()},
        scanned_messages,
        scanned_pages,
    )


def audit_ping_roles(
    messages_by_role_id: dict[str, tuple[str, ...]],
    table_roles: Iterable[RoleInfo],
    scanned_message_count: int,
    scanned_page_count: int,
) -> PingRoleAudit:
    """Compare Discord mentions and database rows strictly by role ID."""

    ping_role_ids = frozenset(messages_by_role_id)
    table_role_ids = frozenset(role.role_id for role in table_roles)
    return PingRoleAudit(
        found_role_ids=ping_role_ids,
        new_role_ids=ping_role_ids - table_role_ids,
        missing_role_ids=table_role_ids - ping_role_ids,
        message_ids_by_role_id=messages_by_role_id,
        scanned_message_count=scanned_message_count,
        scanned_page_count=scanned_page_count,
    )


def load_role_info() -> list[RoleInfo]:
    """Read the comparison fields without changing the database."""

    # Import after loading .env so src.db sees DATABASE_URL during import.
    from src.db import POOL

    try:
        POOL.open(wait=True)
        with POOL.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT role_id, string_tag, member_name, group_name FROM role_info ORDER BY role_id;")
            return [RoleInfo(*row) for row in cursor.fetchall()]
    finally:
        POOL.close()


def display_role(role_id: str, discord_role_names: dict[str, str]) -> str:
    return f"{discord_role_names.get(role_id, '(unknown or deleted Discord role)')} [{role_id}]"


def print_role_list(title: str, roles: Iterable[str]) -> None:
    role_list = list(roles)
    print(f"\n{title} ({len(role_list)}):")
    if role_list:
        for role in role_list:
            print(f"  - {role}")
    else:
        print("  None")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guild-id", default=DEFAULT_GUILD_ID, help="Discord guild ID from the channel URL")
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID, help="Discord channel ID from the channel URL")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="100-message pages to scan, newest first (default: 1)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if Discord and role_info differ (useful in scheduled checks)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_pages < 1:
        raise ValueError("--max-pages must be at least 1")

    load_dotenv(REPO_ROOT / ".env")
    if not os.getenv("USER_AUTH", "").strip():
        raise RuntimeError("USER_AUTH is not configured; add it to .env or the environment")

    from src import content_discord

    messages_by_role_id, scanned_messages, scanned_pages = collect_ping_role_ids(
        lambda before: content_discord.get_channel_messages(
            args.channel_id,
            before_message_id=before,
        ),
        max_pages=args.max_pages,
        delay_seconds=content_discord.REQUEST_DELAY_SECONDS,
    )
    table_roles = load_role_info()
    discord_role_names = {
        str(role["id"]): str(role.get("name", "(unnamed role)"))
        for role in content_discord.get_guild_roles(args.guild_id)
        if isinstance(role.get("id"), (str, int))
    }
    audit = audit_ping_roles(messages_by_role_id, table_roles, scanned_messages, scanned_pages)
    table_role_by_id = {role.role_id: role for role in table_roles}

    print(
        f"Scanned {audit.scanned_message_count} message(s) across {audit.scanned_page_count} page(s) "
        f"in channel {args.channel_id}. Found {len(audit.found_role_ids)} ping role(s); "
        f"role_info has {len(table_roles)} row(s)."
    )
    if args.max_pages == 1:
        print("Note: only the newest page was scanned. Increase --max-pages before treating missing rows as deletions.")

    print_role_list(
        "ADD TO role_info — ping roles missing from the table",
        (
            f"{display_role(role_id, discord_role_names)}; mentioned in message(s): "
            + ", ".join(audit.message_ids_by_role_id[role_id])
            for role_id in sorted(
                audit.new_role_ids, key=lambda role_id: discord_role_names.get(role_id, "").casefold()
            )
        ),
    )
    print_role_list(
        "CHECK/REMOVE — role_info rows absent from scanned ping roles",
        (
            f"{table_role_by_id[role_id].label} [{role_id}]"
            for role_id in sorted(
                audit.missing_role_ids, key=lambda role_id: table_role_by_id[role_id].label.casefold()
            )
        ),
    )

    differences = audit.new_role_ids or audit.missing_role_ids
    return 1 if args.strict and differences else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
