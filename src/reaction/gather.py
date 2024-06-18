import asyncio

import discord

from db.utils import update_given_emote_counts
from src.config.constants import REACT_WAIT_SEC

async def gather_reactions(message: discord.WebhookMessage | discord.InteractionMessage, channel: discord.TextChannel, url: str, role_id:str):
    """
    Gathers the reaction of """
    await asyncio.sleep(REACT_WAIT_SEC)

    message = await channel.fetch_message(message.id)

    count_by_emote = {emote.emoji: emote.count for emote in message.reactions}
    update_given_emote_counts(role_id, url, count_by_emote)
