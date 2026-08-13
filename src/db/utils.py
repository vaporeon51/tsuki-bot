from collections import defaultdict, deque
from dataclasses import dataclass

from src.config.constants import (
    CONTENT_RECOVERY_MAX_GENERATION,
    INITIAL_REACT_CAP,
    RECENTLY_SENT_QUEUE_SIZE,
    REPORT_EMOTE,
    REPORT_THRESHOLD,
    SAMPLING_EXPONENT,
    UPVOTE_EMOTE,
)

from . import POOL

RECENTLY_SENT_QUEUES = defaultdict(lambda: deque(maxlen=RECENTLY_SENT_QUEUE_SIZE))


@dataclass(frozen=True)
class DeadLinkCheckCandidate:
    url: str
    role_labels: tuple[str, ...]


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


def get_live_urls_for_dead_link_check(after_url: str | None, limit: int) -> list[DeadLinkCheckCandidate]:
    """Return the next distinct, eligible URLs with their role labels."""

    with POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH live_rows AS (
                    SELECT
                        cl.url,
                        CASE
                            WHEN ri.member_name IS NOT NULL AND ri.group_name IS NOT NULL
                                THEN ri.member_name || ' (' || ri.group_name || ')'
                            ELSE COALESCE(ri.member_name, ri.group_name, cl.role_id)
                        END AS role_label
                    FROM content_links cl
                    LEFT JOIN role_info ri ON ri.role_id = cl.role_id
                    WHERE cl.is_dead = FALSE
                      AND cl.num_reports < %s
                      AND (%s::TEXT IS NULL OR cl.url > %s)
                )
                SELECT url, array_agg(DISTINCT role_label ORDER BY role_label)
                FROM live_rows
                GROUP BY url
                ORDER BY url ASC
                LIMIT %s;
                """,
                (REPORT_THRESHOLD, after_url, after_url, limit),
            )
            return [DeadLinkCheckCandidate(url=row[0], role_labels=tuple(row[1])) for row in cur.fetchall()]
