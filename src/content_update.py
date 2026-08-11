import asyncio
from datetime import datetime

from src import content_discord, content_ingestion
from src.db import content_update as content_update_db


async def run_content_links_update() -> None:
    """Ingest new content messages and their safe continuations from Discord."""

    print("Starting content update...")
    processed_date = datetime.now()
    last_message_id = await asyncio.to_thread(content_update_db.get_latest_message_id)
    classifier = content_ingestion.ContentMessageClassifier()
    new_links: list[content_ingestion.ContentLinkDraft] = []
    processed_messages = False

    context_messages = await asyncio.to_thread(content_discord.get_messages_around, last_message_id)
    for message in sorted(context_messages, key=lambda item: item["timestamp"]):
        if int(message["id"]) <= int(last_message_id):
            classifier.consume(message)

    while True:
        new_messages = await asyncio.to_thread(content_discord.get_messages_after, last_message_id)
        if not new_messages:
            break
        new_messages.sort(key=lambda message: message["timestamp"])
        for message in new_messages:
            try:
                new_links.extend(classifier.consume(message))
            except Exception:
                print(f"Error with content update on message {message.get('id', 'unknown')}.")
                raise
        processed_messages = True
        last_message_id = str(new_messages[-1]["id"])
        print(f"Processed up to {new_messages[-1]['timestamp']}. Total so far: {len(new_links)}.")
        await asyncio.sleep(content_discord.REQUEST_DELAY_SECONDS)

    if processed_messages:
        await asyncio.to_thread(content_update_db.persist_content_update, processed_date, last_message_id, new_links)

    print("Completed content updates.")
