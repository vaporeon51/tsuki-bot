"""Small in-memory repeat guard for personal feed-derived bias signals."""

import asyncio

from src.db.bias_rater import add_personal_activity
from src.rate_limit import RecentPairRateLimiter

_feed_activity_rate_limiter = RecentPairRateLimiter(cooldown_seconds=5 * 60, capacity=20)


async def record_feed_activity(user_id: int, role_ids: list[str], points: int) -> int:
    """Record each unique user/idol pair at most once per cooldown window."""

    accepted_role_ids = [
        role_id
        for role_id in dict.fromkeys(role_ids)
        if _feed_activity_rate_limiter.allow(user_id, role_id)
    ]
    if not accepted_role_ids:
        return 0
    return await asyncio.to_thread(add_personal_activity, user_id, accepted_role_ids, points)
