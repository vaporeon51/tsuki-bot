import psycopg

from src.config.constants import GUILD_SETTINGS_CACHE_SIZE
from src.utils import LRUCache

from . import CONN_DICT

DEFAULT_INTERVAL = "18 year 1 month"
GUILD_SETTINGS_CACHE = LRUCache(capacity=GUILD_SETTINGS_CACHE_SIZE)


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
    GUILD_SETTINGS_CACHE.put(guild_id, min_age)


def get_min_age(guild_id: int) -> str:
    if min_age := GUILD_SETTINGS_CACHE.get(guild_id):
        return min_age
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
            row = cur.fetchone()
            result = row[0] if row else DEFAULT_INTERVAL
            GUILD_SETTINGS_CACHE.put(guild_id, result)
            return result
