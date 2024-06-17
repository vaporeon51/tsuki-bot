import os
from collections import deque

import psycopg

from src.config.constants import (
    DOWNVOTE_EMOTE,
    INITIAL_REACT_CAP,
    RECENTLY_SENT_QUEUE_SIZE,
    REPORT_EMOTE,
    REPORT_THRESHOLD,
    SAMPLING_EXPONENT,
    UPVOTE_EMOTE,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
CONN_DICT = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
RECENTLY_SENT_QUEUE = deque([""], maxlen=RECENTLY_SENT_QUEUE_SIZE)


def find_closest_role(query: str) -> str | None:
    """Given a query find the best role that match with the query."""
    print(
        f"""
        WITH query AS (
            SELECT to_tsquery('english', regexp_replace(regexp_replace('{query.strip()}', '(\w+)', '\1:*', 'g'), '\s+', ' & ', 'g')) AS search_terms
        ),
        ranked_roles AS (
            SELECT role_id,
                rank() OVER (ORDER BY ts_rank_cd(tsv_string_tag, query.search_terms) DESC) AS rank
            FROM role_info, query
            WHERE
                tsv_string_tag @@ query.search_terms
        )
        SELECT role_id, rank
        FROM ranked_roles, query
        WHERE rank = 1
        ORDER BY random()
        LIMIT 1;
        """
    )
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH query AS (
                    SELECT to_tsquery('english', regexp_replace(regexp_replace('{query.strip()}', '(\w+)', '\1:*', 'g'), '\s+', ' & ', 'g')) AS search_terms
                ),
                ranked_roles AS (
                    SELECT role_id,
                        rank() OVER (ORDER BY ts_rank_cd(tsv_string_tag, query.search_terms) DESC) AS rank
                    FROM role_info, query
                    WHERE
                        tsv_string_tag @@ query.search_terms
                )
                SELECT role_id, rank
                FROM ranked_roles, query
                WHERE rank = 1
                ORDER BY random()
                LIMIT 1;
                """
            )

            # Fetch the first result
            result = cur.fetchone()

            if result:
                return result[0]
            else:
                return None


def get_random_link_for_role(role_id: str) -> str | None:
    """Get a random content link given a role id."""
    recently_sent_queue_str = "(" + ",".join([f"'{item}'" for item in RECENTLY_SENT_QUEUE]) + ")"
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT url
                FROM content_links
                WHERE role_id = '{role_id}'
                AND num_reports < {REPORT_THRESHOLD}
                AND url NOT IN {recently_sent_queue_str}
                ORDER BY RANDOM() * POWER(
                    GREATEST(CAST(LEAST(initial_reaction_count, {INITIAL_REACT_CAP}) + num_upvotes + num_downvotes AS FLOAT), 1.0),
                    {SAMPLING_EXPONENT}
                ) DESC
                LIMIT 1
                """
            )

            # Fetch the first result
            result = cur.fetchone()

            if result:
                RECENTLY_SENT_QUEUE.append(result[0])
                return result[0]
            else:
                return None


def update_given_emote_counts(role_id: str, url: str, count_by_emoji: dict[str, int]) -> None:
    """Update the database for role and URL given the feedback from users."""

    # Subtract 1 from each one to remove bot's react
    upvote_count = count_by_emoji[UPVOTE_EMOTE] - 1
    downvote_count = count_by_emoji[DOWNVOTE_EMOTE] - 1
    report_count = count_by_emoji[REPORT_EMOTE] - 1

    if upvote_count + downvote_count + report_count > 0:
        with psycopg.connect(**CONN_DICT) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_links
                    SET num_upvotes = num_upvotes + %s,
                        num_downvotes = num_downvotes + %s,
                        num_reports = num_reports + %s
                    WHERE url = %s
                    AND role_id = %s
                    """,
                    (upvote_count, downvote_count, report_count, url, role_id),
                )
        print(f"Updated feedback for {role_id} {url}: {(upvote_count, downvote_count, report_count)}")
