import asyncio
from datetime import datetime

from src import content_discord, content_ingestion
from src.db import content_update as content_update_db


async def run_content_links_update() -> None:
    """Ingest new content messages and their safe continuations from Discord."""

    print("Starting content update...")
    last_message_id = await asyncio.to_thread(content_update_db.get_latest_message_id)
    new_messages = await asyncio.to_thread(content_discord.get_messages_after, last_message_id)
    if not new_messages:
        print("Completed content updates: no new messages.")
        return

    classifier = content_ingestion.ContentMessageClassifier()
    context_messages = await asyncio.to_thread(content_discord.get_messages_around, last_message_id)
    for message in sorted(context_messages, key=lambda item: int(item["id"])):
        if int(message["id"]) <= int(last_message_id):
            classifier.consume(message)

    processed_messages = 0
    inserted_links = 0
    while True:
        new_messages.sort(key=lambda message: int(message["id"]))
        page_links: list[content_ingestion.ContentLinkDraft] = []
        for message in new_messages:
            try:
                page_links.extend(classifier.consume(message))
            except Exception:
                print(f"Error with content update on message {message.get('id', 'unknown')}.")
                raise

        last_message_id = str(new_messages[-1]["id"])
        inserted_links += await asyncio.to_thread(
            content_update_db.persist_content_update,
            datetime.now(),
            last_message_id,
            page_links,
        )
        processed_messages += len(new_messages)
        print(
            f"Processed {processed_messages:,} messages through {new_messages[-1]['timestamp']}; "
            f"inserted={inserted_links:,}."
        )
        await asyncio.sleep(content_discord.REQUEST_DELAY_SECONDS)
        new_messages = await asyncio.to_thread(content_discord.get_messages_after, last_message_id)
        if not new_messages:
            break

    print(f"Completed content updates: messages={processed_messages:,} inserted={inserted_links:,}.")
