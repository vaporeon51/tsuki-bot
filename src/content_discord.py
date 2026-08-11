"""Discord channel-history access shared by live content updates and backfills."""

import os
from typing import Any

import requests

KPF_CHANNEL_ID = "124767749099618304"
DISCORD_API_BASE = "https://discord.com/api/v9"
REQUEST_DELAY_SECONDS = 1.2


def _user_auth() -> str:
    user_auth = os.getenv("USER_AUTH", "").strip()
    if not user_auth:
        raise RuntimeError("USER_AUTH is not configured")
    return user_auth


def _get_messages(params: dict[str, str | int]) -> list[dict[str, Any]]:
    """Fetch one channel-history page with the USER_AUTH-compatible endpoint."""

    response = requests.get(
        f"{DISCORD_API_BASE}/channels/{KPF_CHANNEL_ID}/messages",
        params=params,
        headers={"authorization": _user_auth()},
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Discord returned an unexpected channel-history response")
    return [message for message in payload if isinstance(message, dict)]


def get_messages_after(after_message_id: str) -> list[dict[str, Any]]:
    """Get up to 100 messages after a Discord message ID from the content channel."""

    return _get_messages({"limit": 100, "after": after_message_id})


def get_messages_around(message_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Get nearby history to prime a live run's short continuation context."""

    return _get_messages({"limit": min(max(limit, 1), 100), "around": message_id})
