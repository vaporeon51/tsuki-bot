import psycopg
from src.db.guild_settings import get_min_age

from . import CONN_DICT


def get_all_idols_and_groups() -> list[str]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT member_group_array
                FROM role_info
                """,
            )
            return cur.fetchall()