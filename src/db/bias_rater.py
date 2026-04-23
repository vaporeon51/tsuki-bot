import datetime
import random
from typing import Tuple

import psycopg

from . import CONN_DICT

_KST = datetime.timezone(datetime.timedelta(hours=9))


def _today_kst() -> datetime.date:
    """Current date in KST — matches the birthday-feed convention in this codebase."""
    return datetime.datetime.now(_KST).date()

# Only idols with both a member name and an image_url participate in matchups/leaderboards.
# All queries alias role_info as `r` so this predicate is reusable without string surgery.
_ACTIVE_IDOL_PREDICATE = (
    "r.member_name IS NOT NULL AND TRIM(r.member_name) != '' "
    "AND r.image_url IS NOT NULL AND TRIM(r.image_url) != ''"
)

# Rank-based sampling exponent for the first pick in get_matchup (weight ∝ 1/rank^α).
# Scale-invariant: behaves consistently regardless of how wide the user's ELO spread is.
# At α=0.5 over ~200 idols, rank 1 is roughly 14× as likely as rank 200 — gentle bias
# toward the user's higher-ELO idols while keeping plenty of exploration. Raise for
# more top-heavy picks, lower for more uniform.
_FIRST_PICK_ALPHA = 0.5


def calculate_elo_delta(winner_elo: int, loser_elo: int, k: int = 32) -> Tuple[int, int]:
    """Calculate the expected ELO shift for a win/loss."""
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))

    winner_delta = round(k * (1 - expected_winner))
    loser_delta = round(k * (0 - expected_loser))

    return winner_delta, loser_delta


def get_matchup(user_id: int) -> list[tuple[str, str, str, int, str]] | None:
    """Return two idols with close personal ELO.
    Only selects idols that have a non-empty member_name.
    Returns: list of 2 tuples (role_id, member_name, group_name, personal_elo, image_url)
    """
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            # 1. Pick the first idol via rank-weighted sampling (Efraimidis-Spirakis /
            # Gumbel-trick) on personal ELO. weight ∝ 1/rank^α so the user's higher-ELO
            # idols surface more often; everyone still has some chance. Scale-invariant
            # — a user with 20 votes and a user with 2000 see the same bias shape.
            cur.execute(
                f"""
                WITH ranked AS (
                    SELECT r.role_id, r.member_name, r.group_name,
                           COALESCE(u.personal_elo, 1200) AS elo,
                           r.image_url,
                           ROW_NUMBER() OVER (
                               ORDER BY COALESCE(u.personal_elo, 1200) DESC, r.role_id
                           ) AS rnk
                    FROM role_info r
                    LEFT JOIN user_elo u ON r.role_id = u.role_id AND u.user_id = %s
                    WHERE {_ACTIVE_IDOL_PREDICATE}
                )
                SELECT role_id, member_name, group_name, elo, image_url
                FROM ranked
                ORDER BY -ln(GREATEST(RANDOM(), 1e-10)) * POWER(rnk, {_FIRST_PICK_ALPHA}) ASC
                LIMIT 1;
                """,
                (user_id,),
            )
            idol_a = cur.fetchone()

            if not idol_a:
                return None

            role_id_a, _, _, personal_elo_a, _ = idol_a

            # 2. Pick an opponent B using an exponentially weighted sample based on ELO closeness.
            # We sample items with probability proportional to exp(-MAX(elo_diff - 50, 0) / 150).
            # This creates a "flat" probability distribution for anyone within 50 ELO,
            # ensuring they all have an equal uniform chance of being picked. Outside of 50 ELO,
            # it decays less steeply to ensure enough random variety amongst opponents.
            cur.execute(
                f"""
                SELECT r.role_id, r.member_name, r.group_name, COALESCE(u.personal_elo, 1200), r.image_url
                FROM role_info r
                LEFT JOIN user_elo u ON r.role_id = u.role_id AND u.user_id = %s
                WHERE r.role_id != %s
                  AND {_ACTIVE_IDOL_PREDICATE}
                ORDER BY -ln(GREATEST(RANDOM(), 1e-10)) * EXP(GREATEST(ABS(COALESCE(u.personal_elo, 1200) - %s) - 50, 0::numeric) / 100.0) ASC
                LIMIT 1;
                """,
                (user_id, role_id_a, personal_elo_a),
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


def get_global_leaderboard(limit: int = 15) -> list[tuple[str, str, str, int, str]]:
    """Returns top idols by global ELO (role_id, member_name, group_name, global_elo, image_url)."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT r.role_id, r.member_name, r.group_name, r.global_elo, r.image_url
                FROM role_info r
                WHERE {_ACTIVE_IDOL_PREDICATE}
                ORDER BY r.global_elo DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def get_guild_leaderboard(guild_id: int, limit: int = 15) -> list[tuple[str, str, str, int, str]]:
    """Returns top idols by guild ELO for a server (role_id, member_name, group_name, guild_elo, image_url)."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT r.role_id, r.member_name, r.group_name, g.guild_elo, r.image_url
                FROM guild_elo g
                JOIN role_info r ON g.role_id = r.role_id
                WHERE g.guild_id = %s AND {_ACTIVE_IDOL_PREDICATE}
                ORDER BY g.guild_elo DESC
                LIMIT %s;
                """,
                (guild_id, limit),
            )
            return cur.fetchall()


def get_personal_leaderboard(user_id: int, limit: int = 15) -> list[tuple[str, str, str, int, str]]:
    """Returns top idols by personal ELO for a user (role_id, member_name, group_name, personal_elo, image_url)."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT r.role_id, r.member_name, r.group_name, u.personal_elo, r.image_url
                FROM user_elo u
                JOIN role_info r ON u.role_id = r.role_id
                WHERE u.user_id = %s AND {_ACTIVE_IDOL_PREDICATE}
                ORDER BY u.personal_elo DESC
                LIMIT %s;
                """,
                (user_id, limit),
            )
            return cur.fetchall()


# ---------------------------------------------------------------------------
# Daily bracket challenge
# ---------------------------------------------------------------------------


def get_daily_idols(
    date: datetime.date | None = None,
) -> list[tuple[str, str, str, int, str]]:
    """Deterministic set of 8 active idols for a given KST date (default: today).

    Seeded by the date's ordinal so every user who runs /bias daily on the same
    KST day sees the same 8 idols in the same bracket order. Returns an empty
    list if fewer than 8 active idols exist.
    """
    if date is None:
        date = _today_kst()

    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT r.role_id, r.member_name, r.group_name,
                       COALESCE(r.global_elo, 1200), r.image_url
                FROM role_info r
                WHERE {_ACTIVE_IDOL_PREDICATE}
                ORDER BY r.role_id
                """
            )
            all_idols = cur.fetchall()

    if len(all_idols) < 8:
        return []

    rng = random.Random(date.toordinal())
    return rng.sample(all_idols, 8)


def has_completed_daily(user_id: int, date: datetime.date | None = None) -> bool:
    if date is None:
        date = _today_kst()
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM bias_daily_completions
                WHERE user_id = %s AND completion_date = %s;
                """,
                (user_id, date),
            )
            return cur.fetchone() is not None


def record_daily_completion(user_id: int, date: datetime.date | None = None) -> None:
    if date is None:
        date = _today_kst()
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bias_daily_completions (user_id, completion_date)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING;
                """,
                (user_id, date),
            )
