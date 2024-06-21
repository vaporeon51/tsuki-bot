import psycopg

from . import CONN_DICT

DEFAULT_INTERVAL = "18 year 1 month"


def set_min_age(guild_id: int, min_age: int) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT NOW() + interval '{min_age}';")
            cur.execute(
                """
                INSERT INTO guild_settings (guild_id, min_age)
                VALUES (%s, %s)
                ON CONFLICT (guild_id)
                DO UPDATE SET min_age = EXCLUDED.min_age;
                """,
                (guild_id, min_age),
            )


def get_min_age(guild_id: int) -> str:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT min_age
                FROM guild_settings
                WHERE guild_id = %s;
                """,
                (guild_id,),
            )
            result = cur.fetchone()
            if not result:
                return DEFAULT_INTERVAL
            return result[0]
