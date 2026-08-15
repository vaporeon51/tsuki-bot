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


def _get_json(path: str, params: dict[str, str | int] | None = None) -> Any:
    """Fetch a Discord API resource, honoring rate limits and transient failures."""

    transient_attempts = 0
    while True:
        response = None
        try:
            response = requests.get(
                f"{DISCORD_API_BASE}{path}",
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
            return response.json()
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


def get_channel_messages(
    channel_id: str,
    *,
    before_message_id: str | None = None,
    after_message_id: str | None = None,
    around_message_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List one page of messages from a channel.

    Discord accepts at most one message cursor per request.  The returned page
    is newest-first when no cursor is specified (and for ``before`` cursors).
    """

    cursors = [before_message_id, after_message_id, around_message_id]
    if sum(cursor is not None for cursor in cursors) > 1:
        raise ValueError("only one of before_message_id, after_message_id, or around_message_id may be set")

    params: dict[str, str | int] = {"limit": min(max(limit, 1), 100)}
    if before_message_id is not None:
        params["before"] = before_message_id
    elif after_message_id is not None:
        params["after"] = after_message_id
    elif around_message_id is not None:
        params["around"] = around_message_id

    payload = _get_json(f"/channels/{channel_id}/messages", params)
    if not isinstance(payload, list):
        raise RuntimeError("Discord returned an unexpected channel-history response")
    return [message for message in payload if isinstance(message, dict)]


def get_guild_roles(guild_id: str) -> list[dict[str, Any]]:
    """Return role metadata for a guild, including each role's current name."""

    payload = _get_json(f"/guilds/{guild_id}/roles")
    if not isinstance(payload, list):
        raise RuntimeError("Discord returned an unexpected guild-roles response")
    return [role for role in payload if isinstance(role, dict)]


def get_messages_after(after_message_id: str) -> list[dict[str, Any]]:
    """Get up to 100 messages after a Discord message ID from the content channel."""

    return get_channel_messages(KPF_CHANNEL_ID, after_message_id=after_message_id)


def get_messages_around(message_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Get nearby history to prime a live run's short continuation context."""

    return get_channel_messages(KPF_CHANNEL_ID, around_message_id=message_id, limit=limit)
