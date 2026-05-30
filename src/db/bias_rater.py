import datetime
import random
from dataclasses import dataclass
from typing import Tuple

import psycopg

from . import CONN_DICT

_KST = datetime.timezone(datetime.timedelta(hours=9))


def _today_kst() -> datetime.date:
    """Current date in KST — matches the birthday-feed convention in this codebase."""
    return datetime.datetime.now(_KST).date()


def _week_start_kst(date: datetime.date | None = None) -> datetime.date:
    """Monday date for the KST week containing `date`."""
    if date is None:
        date = _today_kst()
    return date - datetime.timedelta(days=date.weekday())


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
LEADERBOARD_SNAPSHOT_LIMIT = 45
GLOBAL_ELO_K = 8
GUILD_ELO_K = 24
PERSONAL_ELO_K = 32


@dataclass(frozen=True)
class LeaderboardEntry:
    role_id: str
    member_name: str
    group_name: str
    elo: int
    image_url: str
    previous_rank: int | None = None


@dataclass(frozen=True)
class Leaderboard:
    entries: list[LeaderboardEntry]
    vote_count: int
    movement_baseline_date: datetime.date | None = None


@dataclass(frozen=True)
class GroupLeaderboardEntry:
    group_name: str
    elo: int
    member_count: int
    ranked_member_count: int
    top_members: list[str]
    image_url: str | None


@dataclass(frozen=True)
class GroupLeaderboard:
    entries: list[GroupLeaderboardEntry]
    vote_count: int
    top_n: int


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
    Records a vote and updates global, guild, and personal ELO and counters.
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
            gw_delta, gl_delta = calculate_elo_delta(gw_elo, gl_elo, GLOBAL_ELO_K)
            sw_delta, sl_delta = calculate_elo_delta(sw_elo, sl_elo, GUILD_ELO_K)
            pw_delta, pl_delta = calculate_elo_delta(pw_elo, pl_elo, PERSONAL_ELO_K)

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
            cur.execute(
                """
                UPDATE role_info
                SET global_win_count = global_win_count + 1,
                    global_match_count = global_match_count + 1
                WHERE role_id = %s;
                """,
                (winner_id,),
            )
            cur.execute(
                """
                UPDATE role_info
                SET global_match_count = global_match_count + 1
                WHERE role_id = %s;
                """,
                (loser_id,),
            )
            cur.execute(
                """
                UPDATE guild_elo
                SET win_count = win_count + 1,
                    match_count = match_count + 1
                WHERE guild_id = %s AND role_id = %s;
                """,
                (guild_id, winner_id),
            )
            cur.execute(
                """
                UPDATE guild_elo
                SET match_count = match_count + 1
                WHERE guild_id = %s AND role_id = %s;
                """,
                (guild_id, loser_id),
            )
            cur.execute(
                """
                UPDATE user_elo
                SET win_count = win_count + 1,
                    match_count = match_count + 1
                WHERE user_id = %s AND role_id = %s;
                """,
                (user_id, winner_id),
            )
            cur.execute(
                """
                UPDATE user_elo
                SET match_count = match_count + 1
                WHERE user_id = %s AND role_id = %s;
                """,
                (user_id, loser_id),
            )

            return gw_delta, gl_delta, sw_delta, sl_delta, pw_delta, pl_delta


def _build_leaderboard(rows, vote_count) -> Leaderboard:
    movement_baseline_date = next((row[6] for row in rows if len(row) > 6), None)
    return Leaderboard(
        entries=[
            LeaderboardEntry(
                role_id=row[0],
                member_name=row[1],
                group_name=row[2],
                elo=row[3],
                image_url=row[4],
                previous_rank=row[5] if len(row) > 5 else None,
            )
            for row in rows
        ],
        vote_count=int(vote_count or 0),
        movement_baseline_date=movement_baseline_date,
    )


def _build_group_leaderboard(rows, vote_count, top_n: int) -> GroupLeaderboard:
    return GroupLeaderboard(
        entries=[
            GroupLeaderboardEntry(
                group_name=row[0],
                elo=row[1],
                member_count=row[2],
                ranked_member_count=row[3],
                top_members=list(row[4] or []),
                image_url=row[5],
            )
            for row in rows
        ],
        vote_count=int(vote_count or 0),
        top_n=top_n,
    )


def get_global_leaderboard(limit: int = 15) -> Leaderboard:
    """Returns top idols by global ELO plus the global vote count."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(global_match_count), 0) / 2 AS vote_count
                FROM role_info;
                """
            )
            vote_count = cur.fetchone()[0]

            cur.execute(
                f"""
                WITH previous_snapshot AS (
                    SELECT MAX(snapshot_date) AS snapshot_date
                    FROM bias_leaderboard_snapshots
                    WHERE scope_type = 'global'
                      AND scope_id = 0
                      AND snapshot_period = 'weekly'
                      AND captured_at <= NOW() - INTERVAL '24 hours'
                ),
                previous_ranks AS (
                    SELECT s.role_id, s.rank, s.snapshot_date
                    FROM bias_leaderboard_snapshots s
                    JOIN previous_snapshot p ON s.snapshot_date = p.snapshot_date
                    WHERE s.scope_type = 'global'
                      AND s.scope_id = 0
                      AND s.snapshot_period = 'weekly'
                )
                SELECT r.role_id,
                       r.member_name,
                       r.group_name,
                       r.global_elo,
                       r.image_url,
                       p.rank AS previous_rank,
                       ps.snapshot_date AS movement_baseline_date
                FROM role_info r
                CROSS JOIN previous_snapshot ps
                LEFT JOIN previous_ranks p ON r.role_id = p.role_id
                WHERE {_ACTIVE_IDOL_PREDICATE}
                ORDER BY r.global_elo DESC, r.member_name, r.role_id
                LIMIT %s;
                """,
                (limit,),
            )
            return _build_leaderboard(cur.fetchall(), vote_count)


def get_global_group_leaderboard(limit: int = 15, top_n: int = 3) -> GroupLeaderboard:
    """Returns top groups by average global ELO of their top N active members."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(global_match_count), 0) / 2 AS vote_count
                FROM role_info;
                """
            )
            vote_count = cur.fetchone()[0]

            cur.execute(
                f"""
                WITH idol_scores AS (
                    SELECT r.group_name,
                           r.member_name,
                           r.image_url,
                           r.global_elo AS elo,
                           COUNT(*) OVER (PARTITION BY r.group_name) AS member_count,
                           ROW_NUMBER() OVER (
                               PARTITION BY r.group_name
                               ORDER BY r.global_elo DESC, r.member_name
                           ) AS member_rank
                    FROM role_info r
                    WHERE {_ACTIVE_IDOL_PREDICATE}
                      AND r.group_name IS NOT NULL
                      AND TRIM(r.group_name) != ''
                )
                SELECT group_name,
                       ROUND(AVG(elo))::int AS elo,
                       MAX(member_count)::int AS member_count,
                       COUNT(*)::int AS ranked_member_count,
                       ARRAY_AGG(member_name ORDER BY elo DESC, member_name) AS top_members,
                       (ARRAY_AGG(image_url ORDER BY elo DESC, member_name))[1] AS image_url
                FROM idol_scores
                WHERE member_rank <= %s
                GROUP BY group_name
                ORDER BY elo DESC, group_name
                LIMIT %s;
                """,
                (top_n, limit),
            )
            return _build_group_leaderboard(cur.fetchall(), vote_count, top_n)


def get_guild_leaderboard(guild_id: int, limit: int = 15) -> Leaderboard:
    """Returns top idols by guild ELO for a server plus the server vote count."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(match_count), 0) / 2 AS vote_count
                FROM guild_elo
                WHERE guild_id = %s;
                """,
                (guild_id,),
            )
            vote_count = cur.fetchone()[0]

            cur.execute(
                f"""
                WITH previous_snapshot AS (
                    SELECT MAX(snapshot_date) AS snapshot_date
                    FROM bias_leaderboard_snapshots
                    WHERE scope_type = 'guild'
                      AND scope_id = %s
                      AND snapshot_period = 'weekly'
                      AND captured_at <= NOW() - INTERVAL '24 hours'
                ),
                previous_ranks AS (
                    SELECT s.role_id, s.rank, s.snapshot_date
                    FROM bias_leaderboard_snapshots s
                    JOIN previous_snapshot p ON s.snapshot_date = p.snapshot_date
                    WHERE s.scope_type = 'guild'
                      AND s.scope_id = %s
                      AND s.snapshot_period = 'weekly'
                )
                SELECT r.role_id,
                       r.member_name,
                       r.group_name,
                       g.guild_elo,
                       r.image_url,
                       p.rank AS previous_rank,
                       ps.snapshot_date AS movement_baseline_date
                FROM guild_elo g
                JOIN role_info r ON g.role_id = r.role_id
                CROSS JOIN previous_snapshot ps
                LEFT JOIN previous_ranks p ON r.role_id = p.role_id
                WHERE g.guild_id = %s AND {_ACTIVE_IDOL_PREDICATE}
                ORDER BY g.guild_elo DESC, r.member_name, r.role_id
                LIMIT %s;
                """,
                (guild_id, guild_id, guild_id, limit),
            )
            return _build_leaderboard(cur.fetchall(), vote_count)


def get_guild_group_leaderboard(guild_id: int, limit: int = 15, top_n: int = 3) -> GroupLeaderboard:
    """Returns top groups by average guild ELO of their top N voted active members."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(match_count), 0) / 2 AS vote_count
                FROM guild_elo
                WHERE guild_id = %s;
                """,
                (guild_id,),
            )
            vote_count = cur.fetchone()[0]

            cur.execute(
                f"""
                WITH idol_scores AS (
                    SELECT r.group_name,
                           r.member_name,
                           r.image_url,
                           g.guild_elo AS elo,
                           COUNT(*) OVER (PARTITION BY r.group_name) AS member_count,
                           ROW_NUMBER() OVER (
                               PARTITION BY r.group_name
                               ORDER BY g.guild_elo DESC, r.member_name
                           ) AS member_rank
                    FROM guild_elo g
                    JOIN role_info r ON g.role_id = r.role_id
                    WHERE g.guild_id = %s
                      AND {_ACTIVE_IDOL_PREDICATE}
                      AND r.group_name IS NOT NULL
                      AND TRIM(r.group_name) != ''
                )
                SELECT group_name,
                       ROUND(AVG(elo))::int AS elo,
                       MAX(member_count)::int AS member_count,
                       COUNT(*)::int AS ranked_member_count,
                       ARRAY_AGG(member_name ORDER BY elo DESC, member_name) AS top_members,
                       (ARRAY_AGG(image_url ORDER BY elo DESC, member_name))[1] AS image_url
                FROM idol_scores
                WHERE member_rank <= %s
                GROUP BY group_name
                ORDER BY elo DESC, group_name
                LIMIT %s;
                """,
                (guild_id, top_n, limit),
            )
            return _build_group_leaderboard(cur.fetchall(), vote_count, top_n)


def get_personal_leaderboard(user_id: int, limit: int = 15) -> Leaderboard:
    """Returns top idols by personal ELO for a user plus the personal vote count."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(match_count), 0) / 2 AS vote_count
                FROM user_elo
                WHERE user_id = %s;
                """,
                (user_id,),
            )
            vote_count = cur.fetchone()[0]

            cur.execute(
                f"""
                WITH previous_snapshot AS (
                    SELECT MAX(snapshot_date) AS snapshot_date
                    FROM bias_leaderboard_snapshots
                    WHERE scope_type = 'personal'
                      AND scope_id = %s
                      AND snapshot_period = 'weekly'
                      AND captured_at <= NOW() - INTERVAL '24 hours'
                ),
                previous_ranks AS (
                    SELECT s.role_id, s.rank, s.snapshot_date
                    FROM bias_leaderboard_snapshots s
                    JOIN previous_snapshot p ON s.snapshot_date = p.snapshot_date
                    WHERE s.scope_type = 'personal'
                      AND s.scope_id = %s
                      AND s.snapshot_period = 'weekly'
                )
                SELECT r.role_id,
                       r.member_name,
                       r.group_name,
                       u.personal_elo,
                       r.image_url,
                       p.rank AS previous_rank,
                       ps.snapshot_date AS movement_baseline_date
                FROM user_elo u
                JOIN role_info r ON u.role_id = r.role_id
                CROSS JOIN previous_snapshot ps
                LEFT JOIN previous_ranks p ON r.role_id = p.role_id
                WHERE u.user_id = %s AND {_ACTIVE_IDOL_PREDICATE}
                ORDER BY u.personal_elo DESC, r.member_name, r.role_id
                LIMIT %s;
                """,
                (user_id, user_id, user_id, limit),
            )
            return _build_leaderboard(cur.fetchall(), vote_count)


def get_personal_group_leaderboard(
    user_id: int, limit: int = 15, top_n: int = 3
) -> GroupLeaderboard:
    """Returns top groups by average personal ELO of their top N voted active members."""
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(match_count), 0) / 2 AS vote_count
                FROM user_elo
                WHERE user_id = %s;
                """,
                (user_id,),
            )
            vote_count = cur.fetchone()[0]

            cur.execute(
                f"""
                WITH idol_scores AS (
                    SELECT r.group_name,
                           r.member_name,
                           r.image_url,
                           u.personal_elo AS elo,
                           COUNT(*) OVER (PARTITION BY r.group_name) AS member_count,
                           ROW_NUMBER() OVER (
                               PARTITION BY r.group_name
                               ORDER BY u.personal_elo DESC, r.member_name
                           ) AS member_rank
                    FROM user_elo u
                    JOIN role_info r ON u.role_id = r.role_id
                    WHERE u.user_id = %s
                      AND {_ACTIVE_IDOL_PREDICATE}
                      AND r.group_name IS NOT NULL
                      AND TRIM(r.group_name) != ''
                )
                SELECT group_name,
                       ROUND(AVG(elo))::int AS elo,
                       MAX(member_count)::int AS member_count,
                       COUNT(*)::int AS ranked_member_count,
                       ARRAY_AGG(member_name ORDER BY elo DESC, member_name) AS top_members,
                       (ARRAY_AGG(image_url ORDER BY elo DESC, member_name))[1] AS image_url
                FROM idol_scores
                WHERE member_rank <= %s
                GROUP BY group_name
                ORDER BY elo DESC, group_name
                LIMIT %s;
                """,
                (user_id, top_n, limit),
            )
            return _build_group_leaderboard(cur.fetchall(), vote_count, top_n)


# ---------------------------------------------------------------------------
# Daily bracket challenge
# ---------------------------------------------------------------------------


def get_daily_idols(
    date: datetime.date | None = None,
    deterministic: bool = False,
) -> list[tuple[str, str, str, int, str]]:
    """Set of 8 active idols for a given KST date (default: today).

    When deterministic=True (default), the sample is seeded by the date's
    ordinal so every user who runs /bias daily on the same KST day sees the
    same 8 idols in the same bracket order. When deterministic=False, the
    sample is freshly random per call — different users will see different
    brackets even on the same day. Returns an empty list if fewer than 8
    active idols exist.
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

    rng = random.Random(date.toordinal()) if deterministic else random.Random()
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


# ---------------------------------------------------------------------------
# Leaderboard snapshots and retention cleanup
# ---------------------------------------------------------------------------


def _fetch_latest_snapshot_rows(
    cur,
    scope_type: str,
    scope_id: int,
    snapshot_period: str,
    before_date: datetime.date,
) -> list[tuple[str, int, int]]:
    cur.execute(
        """
        SELECT role_id, rank, elo
        FROM bias_leaderboard_snapshots
        WHERE scope_type = %s
          AND scope_id = %s
          AND snapshot_period = %s
          AND snapshot_date = (
              SELECT MAX(snapshot_date)
              FROM bias_leaderboard_snapshots
              WHERE scope_type = %s
                AND scope_id = %s
                AND snapshot_period = %s
                AND snapshot_date < %s
          )
        ORDER BY rank;
        """,
        (
            scope_type,
            scope_id,
            snapshot_period,
            scope_type,
            scope_id,
            snapshot_period,
            before_date,
        ),
    )
    return [(row[0], row[1], row[2]) for row in cur.fetchall()]


def _scope_has_snapshot(
    cur,
    scope_type: str,
    scope_id: int,
    snapshot_period: str,
    snapshot_date: datetime.date,
) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM bias_leaderboard_snapshots
        WHERE scope_type = %s
          AND scope_id = %s
          AND snapshot_period = %s
          AND snapshot_date = %s
        LIMIT 1;
        """,
        (scope_type, scope_id, snapshot_period, snapshot_date),
    )
    return cur.fetchone() is not None


def _insert_snapshot_if_changed(
    cur,
    snapshot_date: datetime.date,
    snapshot_period: str,
    scope_type: str,
    scope_id: int,
    rows: list[tuple[str, int, int, int]],
) -> bool:
    """Insert sparse snapshot rows for one scope.

    rows are (role_id, rank, elo, vote_count). Returns True when a snapshot
    was inserted. If this week already has a snapshot, or the current top list
    matches the previous stored snapshot, no rows are written.
    """
    if not rows or _scope_has_snapshot(
        cur, scope_type, scope_id, snapshot_period, snapshot_date
    ):
        return False

    current = [(role_id, rank, elo) for role_id, rank, elo, _ in rows]
    previous = _fetch_latest_snapshot_rows(
        cur, scope_type, scope_id, snapshot_period, snapshot_date
    )
    if previous == current:
        return False

    cur.executemany(
        """
        INSERT INTO bias_leaderboard_snapshots (
            snapshot_date,
            snapshot_period,
            scope_type,
            scope_id,
            role_id,
            rank,
            elo,
            vote_count
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING;
        """,
        [
            (
                snapshot_date,
                snapshot_period,
                scope_type,
                scope_id,
                role_id,
                rank,
                elo,
                vote_count,
            )
            for role_id, rank, elo, vote_count in rows
        ],
    )
    return True


def _fetch_global_snapshot_rows(cur, limit: int) -> list[tuple[str, int, int, int]]:
    cur.execute(
        f"""
        WITH ranked AS (
            SELECT r.role_id,
                   r.global_elo AS elo,
                   ROW_NUMBER() OVER (
                       ORDER BY r.global_elo DESC, r.member_name, r.role_id
                   ) AS rank,
                   (
                       SELECT (COALESCE(SUM(global_match_count), 0) / 2)::int
                       FROM role_info
                   ) AS vote_count
            FROM role_info r
            WHERE {_ACTIVE_IDOL_PREDICATE}
        )
        SELECT role_id, rank::int, elo, vote_count
        FROM ranked
        WHERE rank <= %s
        ORDER BY rank;
        """,
        (limit,),
    )
    return cur.fetchall()


def _fetch_guild_snapshot_rows(
    cur, guild_id: int, limit: int
) -> list[tuple[str, int, int, int]]:
    cur.execute(
        f"""
        WITH ranked AS (
            SELECT r.role_id,
                   g.guild_elo AS elo,
                   ROW_NUMBER() OVER (
                       ORDER BY g.guild_elo DESC, r.member_name, r.role_id
                   ) AS rank,
                   (
                       SELECT (COALESCE(SUM(match_count), 0) / 2)::int
                       FROM guild_elo
                       WHERE guild_id = %s
                   ) AS vote_count
            FROM guild_elo g
            JOIN role_info r ON g.role_id = r.role_id
            WHERE g.guild_id = %s
              AND {_ACTIVE_IDOL_PREDICATE}
        )
        SELECT role_id, rank::int, elo, vote_count
        FROM ranked
        WHERE rank <= %s
        ORDER BY rank;
        """,
        (guild_id, guild_id, limit),
    )
    return cur.fetchall()


def _fetch_personal_snapshot_rows(
    cur, user_id: int, limit: int
) -> list[tuple[str, int, int, int]]:
    cur.execute(
        f"""
        WITH ranked AS (
            SELECT r.role_id,
                   u.personal_elo AS elo,
                   ROW_NUMBER() OVER (
                       ORDER BY u.personal_elo DESC, r.member_name, r.role_id
                   ) AS rank,
                   (
                       SELECT (COALESCE(SUM(match_count), 0) / 2)::int
                       FROM user_elo
                       WHERE user_id = %s
                   ) AS vote_count
            FROM user_elo u
            JOIN role_info r ON u.role_id = r.role_id
            WHERE u.user_id = %s
              AND {_ACTIVE_IDOL_PREDICATE}
        )
        SELECT role_id, rank::int, elo, vote_count
        FROM ranked
        WHERE rank <= %s
        ORDER BY rank;
        """,
        (user_id, user_id, limit),
    )
    return cur.fetchall()


def create_weekly_leaderboard_snapshots(
    snapshot_date: datetime.date | None = None,
    limit: int = LEADERBOARD_SNAPSHOT_LIMIT,
) -> dict[str, int]:
    """Create sparse weekly snapshots for global, guild, and personal idol leaderboards.

    `snapshot_date` is normalized to the Monday of its KST week. For each scope,
    the current top `limit` rows are compared to that scope's latest prior
    weekly snapshot. Rows are inserted only if rank/order/ELO changed.
    """
    snapshot_date = _week_start_kst(snapshot_date)
    snapshot_period = "weekly"
    inserted = {"global": 0, "guild": 0, "personal": 0}

    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            if _insert_snapshot_if_changed(
                cur,
                snapshot_date,
                snapshot_period,
                "global",
                0,
                _fetch_global_snapshot_rows(cur, limit),
            ):
                inserted["global"] += 1

            cur.execute(
                """
                SELECT DISTINCT guild_id
                FROM guild_elo
                WHERE match_count > 0
                ORDER BY guild_id;
                """
            )
            guild_ids = [row[0] for row in cur.fetchall()]
            for guild_id in guild_ids:
                if _insert_snapshot_if_changed(
                    cur,
                    snapshot_date,
                    snapshot_period,
                    "guild",
                    guild_id,
                    _fetch_guild_snapshot_rows(cur, guild_id, limit),
                ):
                    inserted["guild"] += 1

            cur.execute(
                """
                SELECT DISTINCT user_id
                FROM user_elo
                WHERE match_count > 0
                ORDER BY user_id;
                """
            )
            user_ids = [row[0] for row in cur.fetchall()]
            for user_id in user_ids:
                if _insert_snapshot_if_changed(
                    cur,
                    snapshot_date,
                    snapshot_period,
                    "personal",
                    user_id,
                    _fetch_personal_snapshot_rows(cur, user_id, limit),
                ):
                    inserted["personal"] += 1

    return inserted


def cleanup_accumulating_tables(
    snapshot_retention_days: int = 371,
    birthday_message_retention_days: int = 14,
    daily_completion_retention_days: int = 30,
) -> dict[str, int]:
    """Delete old log/snapshot rows from append-only tables."""
    snapshot_cutoff = _today_kst() - datetime.timedelta(days=snapshot_retention_days)
    birthday_cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=birthday_message_retention_days
    )
    daily_cutoff = _today_kst() - datetime.timedelta(days=daily_completion_retention_days)

    deleted: dict[str, int] = {}
    with psycopg.connect(**CONN_DICT) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM bias_leaderboard_snapshots
                WHERE snapshot_date < %s;
                """,
                (snapshot_cutoff,),
            )
            deleted["bias_leaderboard_snapshots"] = cur.rowcount

            cur.execute(
                """
                DELETE FROM birthday_messages
                WHERE post_datetime < %s;
                """,
                (birthday_cutoff,),
            )
            deleted["birthday_messages"] = cur.rowcount

            cur.execute(
                """
                DELETE FROM bias_daily_completions
                WHERE completion_date < %s;
                """,
                (daily_cutoff,),
            )
            deleted["bias_daily_completions"] = cur.rowcount

    return deleted
