import psycopg
import os
import random


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
                LIMIT 1
            """,
                (query,),
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
                ORDER BY RANDOM()
                LIMIT 1
            """,
                (role_id,),
            )

            # Fetch the first result
            result = cur.fetchone()

            if result:
                return result[0]
            else:
                return None
