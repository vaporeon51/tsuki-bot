import asyncio
from itertools import zip_longest
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from the root repository path
WEB_APP_PATH = Path(__file__).parent.resolve()
load_dotenv(WEB_APP_PATH.joinpath(".env").as_posix())


# Local imports after dotenv to ensure environment variables are available
from src.config.constants import DOWNVOTE_EMOTE, REACT_WAIT_SEC, REPORT_EMOTE, UPVOTE_EMOTE
from src.db.utils import find_closest_role, get_random_link_for_role, update_given_emote_counts
from src.reaction.gather import gather_reactions

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(intents=intents, command_prefix="['/tsuki', '/tk', '/feed', '!']", help_command=None)


@bot.event
async def on_ready():
    try:
        print(f"Signed in as { bot.user }")
        await bot.tree.sync()
        print("Successfully synced commands.")
    except Exception as e:
        print(e)


@bot.tree.command(
    name="feed", description="Get kpop content using idol or group name. Use `r` or `random` for random idol."
)
@discord.app_commands.default_permissions(manage_guild=True)
async def feed(interaction: discord.Interaction, query: str | None = None):
    role_id = find_closest_role(query)
    if not role_id:
        text = f"Could not find a role for '{query}'"
        print(text)
        await interaction.response.send_message(text)
        return

    url = get_random_link_for_role(role_id[0])[0]
    if not url:
        text = f"Could not find a content link for role id '{role_id}' given query '{query}'"
        print(text)
        await interaction.response.send_message(text)
        return

    # Send the message and get the sent message
    await interaction.response.send_message(url)
    sent_message = await interaction.original_response()

    # React to the sent message with feedback emotes
    emotes = [UPVOTE_EMOTE, DOWNVOTE_EMOTE, REPORT_EMOTE]
    for emote in emotes:
        await sent_message.add_reaction(emote)

    # Wait for feedback to settle
    await asyncio.sleep(REACT_WAIT_SEC)

    # Fetch the message again to count reactions
    sent_message = await interaction.channel.fetch_message(sent_message.id)

    # Update the table based on feedback
    count_by_emote = {emote.emoji: emote.count for emote in sent_message.reactions}
    update_given_emote_counts(role_id, url, count_by_emote)

@bot.tree.command(name="autofeed", description= "Feast on kpop content, interval for seconds between post, " +
                  "and count for number of posts.")
@discord.app_commands.default_permissions(manage_guild=True)
async def autofeed(interaction: discord.Interaction, query: str | None = None, interval: int = 20, count: int = 5):
    role_ids = find_closest_role(query=query, count=count)
    if len(role_ids) < count and not (query not in ["r", "random"] and len(role_ids) == 1):
        text = f"Could not find enough roles"
        print(text)
        await interaction.response.send_message(text)
        return
    urls = get_random_link_for_role(role_ids=role_ids, count = count)
    if len(urls) < count:
        text = f"Could not find {count} pieces of content"
        print(text)
        await interaction.response.send_message(text)
        return
    
    await interaction.response.defer(thinking=True)

    tasks = []
    for url, role_id in zip_longest(urls, role_ids, fillvalue=role_ids[0]):
        sent_message = await interaction.followup.send(content=url, wait=True)

        emotes = [UPVOTE_EMOTE, DOWNVOTE_EMOTE, REPORT_EMOTE]
        for emote in emotes:
            await sent_message.add_reaction(emote) 

        reaction_gathering_task = asyncio.create_task(gather_reactions(sent_message, url, role_id))
        tasks.append(reaction_gathering_task)

        await asyncio.sleep(interval)
    
    await asyncio.gather(*tasks)

bot.run(TOKEN)
