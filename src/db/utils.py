import csv
import io
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from src.config.constants import (
    CONTENT_RECOVERY_MAX_GENERATION,
    GET_LINKS_EXPORT_CHUNK_BYTES,
    INITIAL_REACT_CAP,
    RECENTLY_SENT_QUEUE_SIZE,
    REPORT_EMOTE,
    REPORT_THRESHOLD,
    SAMPLING_EXPONENT,
    UPVOTE_EMOTE,
)

from . import POOL

RECENTLY_SENT_QUEUES = defaultdict(lambda: deque(maxlen=RECENTLY_SENT_QUEUE_SIZE))

LINK_EXPORT_COLUMNS = (
    "idol",
    "role_id",
    "uploaded_date",
    "author",
    "url",
    "original_url",
)


@dataclass(frozen=True)
class LinkExport:
    paths: list[Path]
    row_count: int


def role_autocomplete_matches(query: str, limit: int = 25) -> list[tuple[str, str]]:
    """Return live-content role choices as ``Idol (Group)`` labels and role IDs."""

    normalized_query = query.strip()
    with POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ri.role_id, ri.member_name, ri.group_name
                FROM role_info AS ri
                WHERE EXISTS (
                    SELECT 1
                    FROM content_links AS cl
                    WHERE cl.role_id = ri.role_id
                      AND cl.is_dead = FALSE
                      AND cl.num_reports < %s
                )
                  AND (
                    %s = ''
                    OR ri.member_name ILIKE '%%' || %s || '%%'
                    OR ri.group_name ILIKE '%%' || %s || '%%'
                  )
                ORDER BY LOWER(ri.member_name), LOWER(ri.group_name), ri.role_id
                LIMIT %s;
                """,
                (REPORT_THRESHOLD, normalized_query, normalized_query, normalized_query, limit),
            )
            rows = cur.fetchall()

    matches: list[tuple[str, str]] = []
    for role_id, member_name, group_name in rows:
        member = str(member_name or "").strip()
        group = str(group_name or "").strip()
        label = f"{member} ({group})" if member and group else member or group
        matches.append((label[:100], str(role_id)))
    return matches


def export_live_links_csv(
    role_id: str,
    output_dir: Path,
    max_chunk_bytes: int = GET_LINKS_EXPORT_CHUNK_BYTES,
) -> LinkExport:
    """Write all eligible links for a role to one or more CSV files."""

    if max_chunk_bytes < 1024:
        raise ValueError("max_chunk_bytes must be at least 1024")

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    row_count = 0
    chunk_index = 0
    output_file = None
    bytes_written = 0

    def serialize(values: tuple[object, ...]) -> bytes:
        row_buffer = io.StringIO(newline="")
        csv.writer(row_buffer).writerow(values)
        return row_buffer.getvalue().encode("utf-8")

    header = serialize(LINK_EXPORT_COLUMNS)

    def open_chunk() -> tuple[Path, object, int]:
        nonlocal chunk_index
        chunk_index += 1
        path = output_dir / f"links-{role_id}-{chunk_index}.csv"
        file = path.open("wb")
        file.write(header)
        paths.append(path)
        return path, file, len(header)

    try:
        with POOL.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        CASE
                            WHEN NULLIF(TRIM(ri.member_name), '') IS NOT NULL
                             AND NULLIF(TRIM(ri.group_name), '') IS NOT NULL
                                THEN TRIM(ri.member_name) || ' (' || TRIM(ri.group_name) || ')'
                            ELSE COALESCE(NULLIF(TRIM(ri.member_name), ''), TRIM(ri.group_name))
                        END AS idol,
                        cl.role_id,
                        cl.uploaded_date,
                        cl.author,
                        cl.url,
                        cl.original_url
                    FROM content_links AS cl
                    JOIN role_info AS ri ON ri.role_id = cl.role_id
                    WHERE cl.role_id = %s
                      AND cl.is_dead = FALSE
                      AND cl.num_reports < %s
                    ORDER BY cl.uploaded_date ASC, cl.content_link_id ASC;
                    """,
                    (role_id, REPORT_THRESHOLD),
                )
                for row in cur:
                    serialized_row = serialize(tuple("" if value is None else value for value in row))
                    if output_file is None:
                        _, output_file, bytes_written = open_chunk()
                    if bytes_written + len(serialized_row) > max_chunk_bytes and bytes_written > len(header):
                        output_file.close()
                        _, output_file, bytes_written = open_chunk()
                    output_file.write(serialized_row)
                    bytes_written += len(serialized_row)
                    row_count += 1
    finally:
        if output_file is not None:
            output_file.close()

    if row_count == 0:
        for path in paths:
            path.unlink(missing_ok=True)
        paths.clear()
    return LinkExport(paths=paths, row_count=row_count)


def get_closest_roles(query: str, min_age: str, count: int = 1) -> list[str] | None:
    """Get up to count closest role IDs to the query."""
    with POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH query AS (
                    SELECT string_to_array(regexp_replace(LOWER(TRIM(%s)), '[^a-zA-Z0-9\s]', '', 'g'), ' ') AS terms
                ),
                matches AS (
                    SELECT role_id,
                        (
                            SELECT COUNT(*)
                            FROM  unnest(member_group_array) AS mga
                            WHERE mga = ANY (query.terms)
                        ) AS match_count
                    FROM role_info, query
                    WHERE NOW() > birthday + %s::INTERVAL
                ),
                maxmatches AS (
                    SELECT MAX(match_count) AS max_matches
                    FROM matches
                )
                SELECT role_id
                FROM matches
                JOIN maxmatches ON matches.match_count = maxmatches.max_matches
                WHERE matches.match_count > 0
                ORDER BY RANDOM()
                LIMIT %s;
                """,
                (query, min_age, count),
            )

            # Fetch the first result
            result = [role[0] for role in cur.fetchall()]

            if not result:
                return None
            return result


def get_random_roles(count: int, min_age: str) -> list[str] | None:
    """Get count number of random role ids"""

    # Determines if cross join is needed for this query
    query_part = ""
    params = ()
    if count > 1:
        query_part = ", generate_series(1, %s)"
        params += (count,)
    params += (min_age, count)

    with POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role_id
                FROM role_info"""
                + query_part
                + """
                WHERE NOW() > birthday + %s::INTERVAL
                ORDER BY random(), role_id DESC
                LIMIT %s
                """,
                params,
            )
            result = [role[0] for role in cur.fetchall()]

            if not result or len(result) < count:
                return None
            return result


def get_latest_links_for_roles(
    num_links: int, skip: int, min_age: str, role_ids: list[str] | None = None
) -> list[tuple[str, str]] | None:
    """Get the latest links for role ids, or all roles if role ids are none."""

    with POOL.connection() as conn:
        with conn.cursor() as cur:
            base_query = """
                WITH bday AS (
                    SELECT role_id, birthday
                    FROM role_info
                    {role_filter}
                ),
                ordered_urls AS (
                    SELECT bday.role_id, cl.url
                    FROM bday
                    JOIN content_links cl
                    ON bday.role_id = cl.role_id
                    WHERE NOT cl.is_dead
                    AND cl.num_reports < %s
                    AND cl.uploaded_date > bday.birthday + %s::INTERVAL
                    ORDER BY cl.uploaded_date DESC
                    LIMIT %s OFFSET %s
                )
                SELECT role_id, url
                FROM ordered_urls;
            """

            role_filter = ""
            params = [REPORT_THRESHOLD, min_age, num_links, skip]
            if role_ids:
                role_filter = "WHERE role_id = ANY(%s)"
                params.insert(0, role_ids)

            query = base_query.format(role_filter=role_filter)
            cur.execute(query, params)
            result = cur.fetchall()

            if not result:
                return None

            return result


def get_random_link_for_each_role(
    role_ids: list[str], min_age: str, *, use_recently_sent_queue: bool = True
) -> list[tuple[str, str]] | None:
    """Get a random content link given a role id."""

    if role_ids is None or len(role_ids) == 0:
        return None

    recently_sent_queue = (
        [item for role in role_ids for item in RECENTLY_SENT_QUEUES[role]] if use_recently_sent_queue else []
    )

    with POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH bday AS (
                    SELECT role_id, birthday
                    FROM role_info
                    WHERE role_info.role_id = ANY(%s)
                ),
                numbered_urls AS (
                    SELECT bday.role_id, cl.url,
                    ROW_NUMBER() OVER (PARTITION BY bday.role_id ORDER BY
                        RANDOM() * POWER(GREATEST(CAST(LEAST(initial_reaction_count / 3, %s) + num_upvotes AS FLOAT), 1.0), %s) DESC)
                        AS row_num
                    FROM bday
                    JOIN content_links cl ON bday.role_id = cl.role_id
                    WHERE NOT cl.is_dead
                    AND cl.num_reports < %s
                    AND (%s OR cl.url != ALL(%s))
                    AND cl.uploaded_date > bday.birthday + %s::INTERVAL
                )

                SELECT role_id, url
                FROM numbered_urls
                WHERE row_num <= (
                    SELECT COUNT(*) FROM (SELECT unnest(%s::TEXT[]) AS id) WHERE id = numbered_urls.role_id
                )
                ORDER BY RANDOM();
                """,
                (
                    role_ids,
                    INITIAL_REACT_CAP,
                    SAMPLING_EXPONENT,
                    REPORT_THRESHOLD,
                    not use_recently_sent_queue,
                    recently_sent_queue,
                    min_age,
                    role_ids,
                ),
            )

            result = cur.fetchall()

            if not result:
                if use_recently_sent_queue:
                    for id in role_ids:
                        RECENTLY_SENT_QUEUES[id].clear()
                return None

            if use_recently_sent_queue and len(result) < len(role_ids):
                role_ids_set = set(role_ids)
                gathered_role_ids_set = set([row[0] for row in result])

                missing_roles = role_ids_set - gathered_role_ids_set

                for id in missing_roles:
                    RECENTLY_SENT_QUEUES[id].clear()

            if use_recently_sent_queue:
                for role, url in result:
                    RECENTLY_SENT_QUEUES[role].append(url)
            return result


def update_given_emote_counts(role_id: str, url: str, count_by_emoji: dict[str, int]) -> None:
    """Update the database for role and URL given the feedback from users."""

    # Subtract 1 from each one to remove bot's react
    upvote_count = count_by_emoji[UPVOTE_EMOTE] - 1
    report_count = count_by_emoji[REPORT_EMOTE] - 1

    if upvote_count + report_count > 0:
        with POOL.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_links
                    SET num_upvotes = num_upvotes + %s,
                        num_reports = num_reports + %s
                    WHERE url = %s
                    AND role_id = %s;
                    """,
                    (upvote_count, report_count, url, role_id),
                )
        print(f"Updated feedback for {role_id} {url}: {(upvote_count, report_count)}")


def mark_url_dead(url: str) -> int:
    """Mark every role using an unavailable URL as dead without changing user reports."""

    with POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE content_links
                SET is_dead = TRUE,
                    is_recovery_exhausted = recovery_generation >= %s
                WHERE url = %s
                  AND is_dead = FALSE;
                """,
                (CONTENT_RECOVERY_MAX_GENERATION, url),
            )
            return cur.rowcount
