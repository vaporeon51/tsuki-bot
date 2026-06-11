import psycopg

from . import CONN_DICT


def normalize_subreddit(subreddit: str) -> str:
    return subreddit.strip().lower()


def set_reddit_feed(guild_id: int, channel_id: int, subreddit: str) -> None:
    subreddit = normalize_subreddit(subreddit)
    if not subreddit:
        raise ValueError("Subreddit cannot be empty.")

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


def get_subscriptions(guild_id: int) -> list[tuple[int, str]]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT guild_id, LOWER(TRIM(subreddit)) AS subreddit, channel_id
                FROM reddit_feeds
                WHERE guild_id = %s
                """,
                (guild_id,),
            )
            results = cur.fetchall()

    return [(channel_id, subreddit) for _, subreddit, channel_id in results]


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


def unset_subreddit_feeds(subreddit: str) -> int:
    subreddit = normalize_subreddit(subreddit)
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM reddit_feeds
                WHERE LOWER(TRIM(subreddit)) = %s;
                """,
                (subreddit,),
            )
            return cur.rowcount


def get_feed_configs() -> list[tuple[int, int, str]]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT guild_id, channel_id, LOWER(TRIM(subreddit)) AS subreddit
                FROM reddit_feeds
                """
            )
            return cur.fetchall()
