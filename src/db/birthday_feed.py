from datetime import datetime, timedelta, timezone
import psycopg

from . import CONN_DICT


def set_birthday_feed(guild_id: int, channel_id: int) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO birthday_feeds (guild_id, channel_id)
                VALUES (%s, %s)
                ON CONFLICT (guild_id, channel_id) DO NOTHING;
                """,
                (guild_id, channel_id),
            )


def get_birthday_feeds(guild_id: int) -> list[int]:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT channel_id
                FROM birthday_feeds
                WHERE guild_id = %s
                """,
                (guild_id,),
            )
            results = cur.fetchall()
    return results


def unset_birthday_feeds(guild_id: int) -> None:
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM birthday_feeds
                WHERE guild_id = %s;
                """,
                (guild_id,),
            )


def log_message(guild_id: int, channel_id: int, role_id: str) -> None:
    post_datetime = datetime.now(timezone.utc)
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO birthday_messages (guild_id, channel_id, role_id, post_datetime)
                VALUES (%s, %s, %s, %s)
                """,
                (guild_id, channel_id, role_id, post_datetime),
            )


def get_recent_messages(guild_id: int) -> list[tuple[int, int]]:
    # Check the last 2 days for relevant posts
    date_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT channel_id, role_id
                FROM birthday_messages
                WHERE guild_id = %s
                AND post_datetime >= %s 
                """,
                (guild_id, date_cutoff),
            )
            return cur.fetchall()


def get_recent_birthdays() -> list[tuple[str, str, str]]:
    """
    Fetch recent birthdays (month and day) that occurred in the past 1 day,
    for members who turned at least 19 years old in the current calendar year or earlier.
    Returns a list of tuples with role_id, member_name, and group_name.
    """
    # Calculate today's and yesterday's month-day combinations
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Format as MM-DD strings for comparison
    today_mm_dd = now.strftime("%m-%d")
    yesterday_mm_dd = yesterday.strftime("%m-%d")

    # Calculate the cutoff year for age 19
    cutoff_year = now.year - 19

    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role_id, member_name, group_name
                FROM role_info
                WHERE TO_CHAR(birthday, 'MM-DD') IN (%s, %s)
                AND EXTRACT(YEAR FROM birthday) <= %s
                AND member_name IS NOT NULL
                AND member_name <> ''
                """,
                (yesterday_mm_dd, today_mm_dd, cutoff_year),
            )
            return cur.fetchall()
