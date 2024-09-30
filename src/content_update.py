import asyncio
import os
from datetime import datetime

import requests
from dateutil import parser

from src.db.content_update import ContentLink, get_latest_message_id, get_role_ids, upsert_content_links_and_update_logs

KPF_CHANNEL_ID = "124767749099618304"
USER_AUTH = os.environ["USER_AUTH"]


def get_latest_messages(after_message_id: str) -> list[dict]:
    """Get a chunk of messages after a certain message id from KPF."""
    headers = {"authorization": USER_AUTH}
    resp = requests.get(
        f"https://discord.com/api/v9/channels/{KPF_CHANNEL_ID}/messages?limit=100&after={after_message_id}",
        headers=headers,
    )
    return resp.json()


def process_message(message_json: dict, valid_roles: list[str], processed_date: datetime) -> list[ContentLink]:
    """Processes an individual message json into content links"""

    # If there are no ping roles or relevant roles then return
    roles = message_json.get("mention_roles")
    if not roles:
        return []

    # TODO: filter out for valid roles once the roles table is being updated regularly
    # relevant_roles = [role for role in roles if role in valid_roles]
    relevant_roles = roles
    if not relevant_roles:
        return []

    # Get links
    links = []
    for embed in message_json["embeds"]:
        if embed["type"] == "gifv":
            links.append(embed["video"]["url"])

    if not links:
        return []

    # Get reactions
    total_reacts = 0
    for react in message_json.get("reactions", []):
        total_reacts += react["count"]

    return [
        ContentLink(
            role_id=role,
            author_id=message_json["author"]["id"],
            author=message_json["author"]["username"],
            uploaded_date=parser.parse(message_json["timestamp"]),
            url=link,
            processed_date=processed_date,
            initial_reaction_count=total_reacts,
        )
        for role in relevant_roles
        for link in links
    ]


async def run_content_links_update() -> None:
    """Main entrypoint for running content update routine."""
    # TODO: look into using discord py library instead of API directly

    print("Starting content update...")
    processed_date = datetime.now()
    last_message_id = get_latest_message_id()
    new_links = []

    # Fetch relevant role ids
    role_ids = get_role_ids()

    # Continuous fetch messages until there are none left
    while new_messages := sorted(get_latest_messages(last_message_id), key=lambda x: x["timestamp"]):
        for message in new_messages:
            if content_links := process_message(message, role_ids, processed_date):
                new_links.extend(content_links)
        # Wait a bit to not trigger rate limit (50 per second)
        await asyncio.sleep(1.2)
        last_message_id = new_messages[-1]["id"]
        print(f"Processed up to {new_messages[-1]['timestamp']}. Total so far: {len(new_links)}.")

    # Bulk upsert the new content links and update log
    if new_links:
        upsert_content_links_and_update_logs(processed_date, last_message_id, new_links)

    print("Completed content updates.")
