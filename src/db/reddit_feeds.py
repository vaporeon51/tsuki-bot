import psycopg

from . import CONN_DICT


def set_channel(guild_id: int, channel_id: int) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reddit_feeds (guild_id, channel_id)
                VALUES (%s, %s)
                ON CONFLICT (guild_id)
                DO UPDATE SET channel_id = EXCLUDED.channel_id;
                """,
                (guild_id, channel_id),
            )


def unset_feed(guild_id: int) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM reddit_feeds
                WHERE guild_id = %s;
                """,
                (guild_id,),
            )


def get_feed_configs() -> list[tuple[int, int]]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT guild_id, channel_id
                FROM reddit_feeds
                """
            )
            return cur.fetchall()
