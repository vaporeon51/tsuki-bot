import random
from typing import Tuple

import psycopg

from . import CONN_DICT


def calculate_elo_delta(winner_elo: int, loser_elo: int, k: int = 32) -> Tuple[int, int]:
    """Calculate the expected ELO shift for a win/loss."""
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))

    winner_delta = round(k * (1 - expected_winner))
    loser_delta = round(k * (0 - expected_loser))

    return winner_delta, loser_delta


def get_matchup(user_id: int) -> list[tuple[str, str, str, int, str]] | None:
    """Return two idols with close global ELO (within +/- 150).
    Only selects idols that have a non-empty member_name.
    Returns: list of 2 tuples (role_id, member_name, group_name, global_elo, image_url)
    """
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            # 1. Pick a random idol A with non-empty member_name
            cur.execute(
                """
                SELECT role_id, member_name, group_name, global_elo, image_url
                FROM role_info
                WHERE member_name IS NOT NULL AND TRIM(member_name) != ''
                ORDER BY RANDOM()
                LIMIT 1;
                """
            )
            idol_a = cur.fetchone()

            if not idol_a:
                return None

            role_id_a, _, _, global_elo_a, _ = idol_a

            # 2. Find a close opponent B within +/- 150 ELO
            cur.execute(
                """
                WITH close_matches AS (
                    SELECT role_id, member_name, group_name, global_elo, image_url
                    FROM role_info
                    WHERE role_id != %s
                      AND member_name IS NOT NULL AND TRIM(member_name) != ''
                      AND global_elo BETWEEN %s AND %s
                )
                SELECT * FROM close_matches
                ORDER BY RANDOM()
                LIMIT 1;
                """,
                (role_id_a, global_elo_a - 150, global_elo_a + 150),
            )
            idol_b = cur.fetchone()

            # If no close match found, just pick any random opponent
            if not idol_b:
                cur.execute(
                    """
                    SELECT role_id, member_name, group_name, global_elo, image_url
                    FROM role_info
                    WHERE role_id != %s
                      AND member_name IS NOT NULL AND TRIM(member_name) != ''
                    ORDER BY RANDOM()
                    LIMIT 1;
                    """,
                    (role_id_a,),
                )
                idol_b = cur.fetchone()

            if not idol_b:
                return None  # Only 1 idol exists in DB

            matchup = [idol_a, idol_b]
            random.shuffle(matchup)  # Randomize which one is left/right
            return matchup


def record_vote(
    user_id: int, guild_id: int, winner_id: str, loser_id: str
) -> tuple[int, int, int, int, int, int]:
    """
    Records a vote and updates global, guild, and personal ELO.
    Returns (global_winner_delta, global_loser_delta,
             guild_winner_delta, guild_loser_delta,
             personal_winner_delta, personal_loser_delta).
    """
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            # 1. Ensure per-user and per-guild rows exist (default 1200)
            cur.execute(
                """
                INSERT INTO user_elo (user_id, role_id)
                VALUES (%s, %s), (%s, %s)
                ON CONFLICT (user_id, role_id) DO NOTHING;
                """,
                (user_id, winner_id, user_id, loser_id),
            )
            cur.execute(
                """
                INSERT INTO guild_elo (guild_id, role_id)
                VALUES (%s, %s), (%s, %s)
                ON CONFLICT (guild_id, role_id) DO NOTHING;
                """,
                (guild_id, winner_id, guild_id, loser_id),
            )

            # 2. Read current ELOs for all three scopes
            cur.execute(
                "SELECT role_id, global_elo FROM role_info WHERE role_id IN (%s, %s);",
                (winner_id, loser_id),
            )
            global_elos = {row[0]: row[1] for row in cur.fetchall()}
            gw_elo = global_elos[winner_id]
            gl_elo = global_elos[loser_id]

            cur.execute(
                """
                SELECT role_id, guild_elo FROM guild_elo
                WHERE guild_id = %s AND role_id IN (%s, %s);
                """,
                (guild_id, winner_id, loser_id),
            )
            guild_elos = {row[0]: row[1] for row in cur.fetchall()}
            sw_elo = guild_elos[winner_id]
            sl_elo = guild_elos[loser_id]

            cur.execute(
                """
                SELECT role_id, personal_elo FROM user_elo
                WHERE user_id = %s AND role_id IN (%s, %s);
                """,
                (user_id, winner_id, loser_id),
            )
            personal_elos = {row[0]: row[1] for row in cur.fetchall()}
            pw_elo = personal_elos[winner_id]
            pl_elo = personal_elos[loser_id]

            # 3. Calculate deltas
            gw_delta, gl_delta = calculate_elo_delta(gw_elo, gl_elo)
            sw_delta, sl_delta = calculate_elo_delta(sw_elo, sl_elo)
            pw_delta, pl_delta = calculate_elo_delta(pw_elo, pl_elo)

            # 4. Update tables
            cur.execute(
                "UPDATE role_info SET global_elo = global_elo + %s WHERE role_id = %s;",
                (gw_delta, winner_id),
            )
            cur.execute(
                "UPDATE role_info SET global_elo = global_elo + %s WHERE role_id = %s;",
                (gl_delta, loser_id),
            )
            cur.execute(
                """
                UPDATE guild_elo SET guild_elo = guild_elo + %s
                WHERE guild_id = %s AND role_id = %s;
                """,
                (sw_delta, guild_id, winner_id),
            )
            cur.execute(
                """
                UPDATE guild_elo SET guild_elo = guild_elo + %s
                WHERE guild_id = %s AND role_id = %s;
                """,
                (sl_delta, guild_id, loser_id),
            )
            cur.execute(
                """
                UPDATE user_elo SET personal_elo = personal_elo + %s
                WHERE user_id = %s AND role_id = %s;
                """,
                (pw_delta, user_id, winner_id),
            )
            cur.execute(
                """
                UPDATE user_elo SET personal_elo = personal_elo + %s
                WHERE user_id = %s AND role_id = %s;
                """,
                (pl_delta, user_id, loser_id),
            )

            return gw_delta, gl_delta, sw_delta, sl_delta, pw_delta, pl_delta


def get_global_leaderboard(limit: int = 10) -> list[tuple[str, str, int]]:
    """Returns top idols by global ELO (member_name, group_name, global_elo)."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT member_name, group_name, global_elo
                FROM role_info
                WHERE member_name IS NOT NULL AND TRIM(member_name) != ''
                ORDER BY global_elo DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def get_guild_leaderboard(guild_id: int, limit: int = 10) -> list[tuple[str, str, int]]:
    """Returns top idols by guild ELO for a server (member_name, group_name, guild_elo)."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.member_name, r.group_name, g.guild_elo
                FROM guild_elo g
                JOIN role_info r ON g.role_id = r.role_id
                WHERE g.guild_id = %s AND r.member_name IS NOT NULL AND TRIM(r.member_name) != ''
                ORDER BY g.guild_elo DESC
                LIMIT %s;
                """,
                (guild_id, limit),
            )
            return cur.fetchall()


def get_personal_leaderboard(user_id: int, limit: int = 10) -> list[tuple[str, str, int]]:
    """Returns top idols by personal ELO for a user (member_name, group_name, personal_elo)."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.member_name, r.group_name, u.personal_elo
                FROM user_elo u
                JOIN role_info r ON u.role_id = r.role_id
                WHERE u.user_id = %s AND r.member_name IS NOT NULL AND TRIM(r.member_name) != ''
                ORDER BY u.personal_elo DESC
                LIMIT %s;
                """,
                (user_id, limit),
            )
            return cur.fetchall()
