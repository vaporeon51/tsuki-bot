import os

import psycopg

from src.config.constants import DOWNVOTE_EMOTE, REPORT_EMOTE, UPVOTE_EMOTE, REPORT_THRESHOLD

DATABASE_URL = os.environ.get("DATABASE_URL")
CONN_DICT = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)


def find_closest_role(query: str) -> str | None:
    """Given a query find the best role that match with the query."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role_id
                FROM role_info
                WHERE string_tag ILIKE %s
                ORDER BY RANDOM()
                LIMIT 1
            """,
                (f"%{query}%",),
            )

            # Fetch the first result
            result = cur.fetchone()

            if result:
                return result[0]
            else:
                return None


def get_random_link_for_role(role_id: str) -> str | None:
    """Get a random content link given a role id."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT url
                FROM content_links
                WHERE role_id = %s
                AND num_reports < %s
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (role_id, REPORT_THRESHOLD),
            )

            # Fetch the first result
            result = cur.fetchone()

            if result:
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
