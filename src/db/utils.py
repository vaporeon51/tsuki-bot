import os

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL")
CONN_DICT = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)


def find_closest_role(query: str) -> str | None:
    """Given a query find the best role that match with the query."""
    search_term = query.replace(" ", " | ")
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH query AS (
                    SELECT to_tsquery('english', 'ive | yujin') AS search_terms 
                )
                SELECT role_id,
                    ts_rank_cd(tsv_member_name, query.search_terms) +
                    ts_rank_cd(tsv_group_name, query.search_terms) AS rank
                FROM role_info
                WHERE
                    (tsv_member_name @@ query.search_terms)
                    AND
                    (tsv_group_name @@ query.search_terms)
                ORDER BY rank DESC
                LIMIT 1
            """,
                (search_term),
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
