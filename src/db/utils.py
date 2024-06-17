import os

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL")
CONN_DICT = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)


def find_closest_role(query: str) -> str | None:
    """Given a query find the best role that match with the query."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH query AS (
                    SELECT to_tsquery('english',
                            regexp_replace(
                                regexp_replace(%s, '\s+', ' | ', 'g'),
                                '[^a-zA-Z0-9|\s]+', '', 'g')) AS search_terms
                ),
                ranked_roles AS (
                    SELECT role_id, member_name, group_name,
                        ts_rank_cd(tsv_member_name, query.search_terms) +
                        ts_rank_cd(tsv_group_name, query.search_terms) AS r,
                        rank() OVER (ORDER BY ts_rank_cd(tsv_member_name, query.search_terms) +
                        ts_rank_cd(tsv_group_name, query.search_terms) DESC) AS rank
                    FROM role_info, query
                    WHERE
                        tsv_member_name @@ query.search_terms
                        OR
                        tsv_group_name @@ query.search_terms
                )
                SELECT role_id, member_name, group_name, rank, r
                FROM ranked_roles
                WHERE rank = 1
                ORDER BY random();
            """,
                (query),
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
