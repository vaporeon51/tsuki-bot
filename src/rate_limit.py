import time
from enum import Enum


class Decision(Enum):
    ALLOW = "allow"
    DENY_NOTIFY = "deny_notify"  # throttled; caller should post the "slow down" notice
    DENY_SILENT = "deny_silent"  # throttled and already notified recently; stay quiet


class ChannelRateLimiter:
    """Per-channel token-bucket limiter (in-memory, single process).

    Allows a short burst of up to ``capacity`` replies, then throttles to roughly
    one reply per ``refill_seconds``. When throttled, it tells the caller to post
    a notice at most once per ``notify_cooldown`` seconds per channel so the
    "slow down" message doesn't itself become spam.
    """

    def __init__(self, capacity: int, refill_seconds: float, notify_cooldown: float):
        self.capacity = capacity
        self.refill_seconds = refill_seconds
        self.notify_cooldown = notify_cooldown
        self._buckets: dict[int, tuple[float, float]] = {}  # channel_id -> (tokens, last_ts)
        self._last_notified: dict[int, float] = {}  # channel_id -> last notice ts

    def check(self, channel_id: int) -> Decision:
        # Atomic under asyncio: there is no await between reading and writing the
        # bucket, so concurrent mentions can't race here.
        now = time.monotonic()  # monotonic clock: immune to system time changes
        tokens, last = self._buckets.get(channel_id, (float(self.capacity), now))
        tokens = min(self.capacity, tokens + (now - last) / self.refill_seconds)

        if tokens >= 1:
            self._buckets[channel_id] = (tokens - 1, now)
            return Decision.ALLOW

        self._buckets[channel_id] = (tokens, now)  # still record refill progress
        if now - self._last_notified.get(channel_id, float("-inf")) >= self.notify_cooldown:
            self._last_notified[channel_id] = now
            return Decision.DENY_NOTIFY
        return Decision.DENY_SILENT
