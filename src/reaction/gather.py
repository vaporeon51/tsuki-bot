import asyncio

import discord

from src.config.constants import REACT_WAIT_SEC
from src.db.utils import mark_url_dead, update_given_emote_counts
from src.utils import is_message_broken_link


async def gather_dead_link(message: discord.Message, url: str) -> None:
    """
    Gather only deadlink no reactions.
    """

    await asyncio.sleep(30)

    message = await message.channel.fetch_message(message.id)

    if is_message_broken_link(message):
        marked_count = await asyncio.to_thread(mark_url_dead, url)
        print(f"URL {url} is broken; marked {marked_count} content link(s) dead.")


async def gather_reactions(message: discord.Message, url: str, role_id: str) -> None:
    """
    Gathers the reaction of message
    """
    await asyncio.sleep(REACT_WAIT_SEC)

    message = await message.channel.fetch_message(message.id)

    if is_message_broken_link(message):
        marked_count = await asyncio.to_thread(mark_url_dead, url)
        print(f"URL {url} is broken; marked {marked_count} content link(s) dead.")
        return

    count_by_emote = {emote.emoji: emote.count for emote in message.reactions}
    await asyncio.to_thread(update_given_emote_counts, role_id, url, count_by_emote)
