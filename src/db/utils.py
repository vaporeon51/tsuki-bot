import os
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

DATABASE_URL = os.environ.get("DATABASE_URL")
CONN_DICT = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
RECENTLY_SENT_QUEUES = defaultdict(lambda: deque([""], maxlen=RECENTLY_SENT_QUEUE_SIZE))


def find_closest_role(query: str | None) -> str | None:
    """Given a query find the best role that match with the query."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            if not query or query.lower() in ["r", "random"]:
                cur.execute(
                    """
                    SELECT role_id
                    FROM role_info
                    ORDER BY random()
                    LIMIT 1;
                    """
                )
            else:
                cur.execute(
                    f"""
                    WITH query AS (
                        SELECT to_tsquery('english', regexp_replace(regexp_replace(regexp_replace('{query.strip()}', '[^a-zA-Z0-9\s]', '', 'g'), '(\w+)', '\\1:*', 'g'), '\s+', ' & ', 'g')) AS search_terms
                    ),
                    ranked_roles AS (
                        SELECT role_id,
                            rank() OVER (ORDER BY ts_rank_cd(tsv_string_tag, query.search_terms) DESC) AS rank
                        FROM role_info, query
                        WHERE
                            tsv_string_tag @@ query.search_terms
                            AND
                            NOW() > birthday + interval '18 year 1 month'
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
    recently_sent_queue_str = "(" + ",".join([f"'{item}'" for item in RECENTLY_SENT_QUEUES[role_id]]) + ")"
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH bday_temp AS (
                    SELECT birthday
                    FROM role_info
                    WHERE role_id = '{role_id}'
                )
                SELECT url
                FROM content_links, bday_temp
                WHERE role_id = '{role_id}'
                AND num_reports < {REPORT_THRESHOLD}
                AND url NOT IN {recently_sent_queue_str}
                AND uploaded_date > bday_temp.birthday + interval '18 year 1 month'
                ORDER BY RANDOM() * POWER(
                    GREATEST(CAST(LEAST(initial_reaction_count / 3, {INITIAL_REACT_CAP}) + num_upvotes AS FLOAT), 1.0),
                    {SAMPLING_EXPONENT}
                ) DESC
                LIMIT 1
                """
            )

            # Fetch the first result
            result = cur.fetchone()

            if result:
                RECENTLY_SENT_QUEUES[role_id].append(result[0])
                return result[0]
            else:
                # If there are none left for this role then reset the queue
                RECENTLY_SENT_QUEUES[role_id] = deque([""], maxlen=RECENTLY_SENT_QUEUE_SIZE)
                return None


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
