import asyncio

import discord

from src.config.constants import REACT_WAIT_SEC
from src.db.utils import report_broken_link_url, update_given_emote_counts
from src.utils import is_message_broken_link


async def gather_reactions(message: discord.Message, url: str, role_id: str) -> None:
    """
    Gathers the reaction of message
    """
    await asyncio.sleep(REACT_WAIT_SEC)

    message = await message.channel.fetch_message(message.id)

    if is_message_broken_link(message):
        print(f"URL {url} is broken and incrementing their report counts.")
        report_broken_link_url(url=url)
        return

    count_by_emote = {emote.emoji: emote.count for emote in message.reactions}
    update_given_emote_counts(role_id, url, count_by_emote)
