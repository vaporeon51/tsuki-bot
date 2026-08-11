"""Discord channel-history access for live content updates."""

import os
import time
from typing import Any

import requests

KPF_CHANNEL_ID = "124767749099618304"
DISCORD_API_BASE = "https://discord.com/api/v9"
REQUEST_DELAY_SECONDS = 1.2
MAX_TRANSIENT_RETRIES = 8
MAX_RETRY_DELAY_SECONDS = 60.0


def _user_auth() -> str:
    user_auth = os.getenv("USER_AUTH", "").strip()
    if not user_auth:
        raise RuntimeError("USER_AUTH is not configured")
    return user_auth


def _get_messages(params: dict[str, str | int]) -> list[dict[str, Any]]:
    """Fetch one history page, honoring rate limits and retrying transient failures."""

    transient_attempts = 0
    while True:
        response = None
        try:
            response = requests.get(
                f"{DISCORD_API_BASE}/channels/{KPF_CHANNEL_ID}/messages",
                params=params,
                headers={"authorization": _user_auth()},
                timeout=(10, 30),
            )
            if response.status_code == 429:
                try:
                    retry_after = float(response.json().get("retry_after", 0))
                except (AttributeError, TypeError, ValueError):
                    retry_after = 0
                if retry_after <= 0:
                    try:
                        retry_after = float(response.headers.get("Retry-After", REQUEST_DELAY_SECONDS))
                    except (TypeError, ValueError):
                        retry_after = REQUEST_DELAY_SECONDS
                retry_after = max(retry_after, REQUEST_DELAY_SECONDS)
                print(f"Discord rate limited the history scan; retrying in {retry_after:.1f}s.")
                time.sleep(retry_after)
                continue

            if 500 <= response.status_code < 600:
                raise requests.HTTPError(f"Discord returned HTTP {response.status_code}", response=response)

            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                raise RuntimeError(f"Discord history request was rejected with HTTP {response.status_code}") from error
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Discord returned an unexpected channel-history response")
            return [message for message in payload if isinstance(message, dict)]
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as error:
            transient_attempts += 1
            if transient_attempts > MAX_TRANSIENT_RETRIES:
                raise RuntimeError(
                    f"Discord history request failed after {MAX_TRANSIENT_RETRIES} retries: {error}"
                ) from error
            retry_after = min(2 ** (transient_attempts - 1), MAX_RETRY_DELAY_SECONDS)
            print(
                f"Discord history request failed ({type(error).__name__}); "
                f"retrying in {retry_after:.1f}s ({transient_attempts}/{MAX_TRANSIENT_RETRIES})."
            )
            time.sleep(retry_after)
        finally:
            if response is not None:
                response.close()


def get_messages_after(after_message_id: str) -> list[dict[str, Any]]:
    """Get up to 100 messages after a Discord message ID from the content channel."""

    return _get_messages({"limit": 100, "after": after_message_id})


def get_messages_around(message_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Get nearby history to prime a live run's short continuation context."""

    return _get_messages({"limit": min(max(limit, 1), 100), "around": message_id})
