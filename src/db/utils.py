from collections import defaultdict, deque

import psycopg

from src.config.constants import (
    INITIAL_REACT_CAP,
    RECENTLY_SENT_QUEUE_SIZE,
    REPORT_EMOTE,
    REPORT_THRESHOLD,
    SAMPLING_EXPONENT,
    UPVOTE_EMOTE,
)

from . import CONN_DICT

RECENTLY_SENT_QUEUES = defaultdict(lambda: deque(maxlen=RECENTLY_SENT_QUEUE_SIZE))


def get_closest_roles(query: str, min_age: str, count: int = 1) -> list[str] | None:
    """Get up to count closest role IDs to the query."""
    with psycopg.connect(**CONN_DICT) as conn:
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

    with psycopg.connect(**CONN_DICT) as conn:
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


def get_random_link_for_each_role(role_ids: list[str], min_age: str) -> list[tuple[str, str]] | None:
    """Get a random content link given a role id."""

    if role_ids is None or len(role_ids) == 0:
        return None

    recently_sent_queue = [item for role in role_ids for item in RECENTLY_SENT_QUEUES[role]]
    print(min_age)

    with psycopg.connect(**CONN_DICT) as conn:
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
                    WHERE cl.num_reports < %s
                    AND cl.url != ALL(%s)
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
                    recently_sent_queue,
                    min_age,
                    role_ids,
                ),
            )

            result = cur.fetchall()

            if not result:
                for id in role_ids:
                    RECENTLY_SENT_QUEUES[id].clear()
                    return None

            if len(result) < len(role_ids):
                role_ids_set = set(role_ids)
                gathered_role_ids_set = set([row[0] for row in result])

                missing_roles = role_ids_set - gathered_role_ids_set

                for id in missing_roles:
                    RECENTLY_SENT_QUEUES[id].clear()

            for role, url in result:
                RECENTLY_SENT_QUEUES[role].append(url)
            return result


def update_given_emote_counts(role_id: str, url: str, count_by_emoji: dict[str, int]) -> None:
    """Update the database for role and URL given the feedback from users."""

    # Subtract 1 from each one to remove bot's react
    upvote_count = count_by_emoji[UPVOTE_EMOTE] - 1
    report_count = count_by_emoji[REPORT_EMOTE] - 1

    if upvote_count + report_count > 0:
        with psycopg.connect(**CONN_DICT) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_links
                    SET num_upvotes = num_upvotes + %s,
                        num_reports = num_reports + %s
                    WHERE url = %s
                    AND role_id = %s
                    """,
                    (upvote_count, report_count, url, role_id),
                )
        print(f"Updated feedback for {role_id} {url}: {(upvote_count, report_count)}")
