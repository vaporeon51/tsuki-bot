import psycopg

from src.config.constants import GUILD_SETTINGS_CACHE_SIZE
from src.utils import LRUCache

from . import CONN_DICT

REDDIT_FEEDS_CACHE = LRUCache(capacity=GUILD_SETTINGS_CACHE_SIZE)


def set_reddit_feed(guild_id: int, channel_id: int, subreddit: str) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reddit_feeds (guild_id, channel_id, subreddit)
                VALUES (%s, %s, %s)
                ON CONFLICT (guild_id, channel_id, subreddit) DO NOTHING;
                """,
                (guild_id, channel_id, subreddit),
            )
            REDDIT_FEEDS_CACHE.invalidate(guild_id)


def get_subscriptions(guild_id: int) -> list[tuple[int, str]]:
    cached_results = REDDIT_FEEDS_CACHE.get(guild_id)
    if cached_results is not None:
        return cached_results
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT guild_id, subreddit, channel_id
                FROM reddit_feeds
                WHERE guild_id = %s
                """,
                (guild_id,),
            )
            results = cur.fetchall()

    results = [(channel_id, subreddit) for _, subreddit, channel_id in results]
    REDDIT_FEEDS_CACHE.put(guild_id, results)
    return results


def unset_feeds(guild_id: int) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM reddit_feeds
                WHERE guild_id = %s;
                """,
                (guild_id,),
            )
            REDDIT_FEEDS_CACHE.invalidate(guild_id)


def get_feed_configs() -> list[tuple[int, int]]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT guild_id, channel_id, subreddit
                FROM reddit_feeds
                """
            )
            return cur.fetchall()
