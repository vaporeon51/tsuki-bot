import psycopg

from . import CONN_DICT


def add_stat_count(stat: str, value: int = 1) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bot_stats (stat_name, value)
                VALUES (%s, %s)
                ON CONFLICT (stat_name)
                DO UPDATE SET value = bot_stats.value + %s
            """,
                (stat, value, value),
            )
