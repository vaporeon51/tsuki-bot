import asyncio

import discord

from src.db.utils import mark_url_dead
from src.utils import is_message_broken_link


async def gather_dead_link(
    message: discord.Message,
    url: str,
    *,
    wait_seconds: float = 30,
) -> int:
    """
    Gather only deadlink no reactions and return the number of rows marked.
    """

    await asyncio.sleep(wait_seconds)
    checked_message = await message.channel.fetch_message(message.id)

    if is_message_broken_link(checked_message):
        marked_count = await asyncio.to_thread(mark_url_dead, url)
        print(f"URL {url} is broken; marked {marked_count} content link(s) dead.")
        return marked_count

    return 0
