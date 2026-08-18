from collections.abc import Sequence
from datetime import datetime
from typing import Any

import psycopg

from src.content_ingestion import ContentLinkDraft

from . import POOL

INSERT_CONTENT_LINK = """
    INSERT INTO content_links
        (role_id, author_id, author, uploaded_date, url, initial_reaction_count,
         num_upvotes, num_reports, processed_date, source_message_id,
         root_message_id, source_kind)
    VALUES
        (%s, %s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s)
    ON CONFLICT (source_message_id, role_id, url)
        WHERE source_message_id IS NOT NULL DO NOTHING;
"""


def get_known_role_ids() -> frozenset[str]:
    """Return IDs that are valid content-link roles."""

    with POOL.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role_id FROM role_info;")
            return frozenset(str(row[0]) for row in cursor.fetchall())


def get_latest_message_id() -> str:
    with POOL.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT last_message_id
                FROM update_log
                ORDER BY processed_date DESC
                LIMIT 1;
                """
            )
            result = cursor.fetchone()
    if result is None:
        raise RuntimeError("update_log does not contain an initial Discord cursor")
    return str(result[0])


def content_link_params(link: ContentLinkDraft, processed_date: datetime) -> tuple[Any, ...]:
    return (
        link.role_id,
        link.author_id,
        link.author,
        link.uploaded_date,
        link.url,
        link.initial_reaction_count,
        processed_date,
        link.source_message_id,
        link.root_message_id,
        link.source_kind,
    )


def _insert_content_links(
    cursor: psycopg.Cursor[Any], processed_date: datetime, links: Sequence[ContentLinkDraft]
) -> int:
    if not links:
        return 0
    cursor.executemany(INSERT_CONTENT_LINK, (content_link_params(link, processed_date) for link in links))
    return cursor.rowcount


def reconcile_content_links(processed_date: datetime, links: list[ContentLinkDraft]) -> int:
    """Insert missing links from the recent live lookback without moving its cursor."""

    with POOL.connection() as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                return _insert_content_links(cursor, processed_date, links)


def persist_content_update(processed_date: datetime, last_message_id: str, links: list[ContentLinkDraft]) -> int:
    """Atomically insert one page of links and advance the live Discord cursor."""

    with POOL.connection() as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                inserted_count = _insert_content_links(cursor, processed_date, links)
                cursor.execute(
                    """
                    INSERT INTO update_log (processed_date, last_message_id, rows_inserted)
                    VALUES (%s, %s, %s);
                    """,
                    (processed_date, last_message_id, inserted_count),
                )

    return inserted_count
