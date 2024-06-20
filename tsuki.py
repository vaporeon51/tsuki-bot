import asyncio
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from the root repository path
WEB_APP_PATH = Path(__file__).parent.resolve()
load_dotenv(WEB_APP_PATH.joinpath(".env").as_posix())


# Local imports after dotenv to ensure environment variables are available
from src.config.constants import REACT_WAIT_SEC, REPORT_EMOTE, UPVOTE_EMOTE
from src.db.utils import find_closest_role, get_random_link_for_role, update_given_emote_counts

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

    print(f"Currently in {len(bot.guilds)} servers:")
    for server in bot.guilds:
        print("Server name:", server.name, ", owner:", server.owner.name)


@bot.tree.command(
    name="feed", description="Get kpop content using idol or group name. Use `r` or `random` for random idol."
)
async def feed(interaction: discord.Interaction, query: str | None = None):
    role_id = find_closest_role(query)
    if not role_id:
        text = f"Could not find a role for `{query}`. This message will disappear in 30s."
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return
    url = get_random_link_for_role(role_id)
    if not url:
        text = f"Could not find a content link for role id `{role_id}` given query `{query}`. This message will disappear in 30s."
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return

    # Send the message and get the sent message
    await interaction.response.send_message(url)
    sent_message = await interaction.original_response()

    # React to the sent message with feedback emotes
    emotes = [UPVOTE_EMOTE, REPORT_EMOTE]
    for emote in emotes:
        await sent_message.add_reaction(emote)

    # Wait for feedback to settle
    await asyncio.sleep(REACT_WAIT_SEC)

    # Fetch the message again to count reactions
    sent_message = await interaction.channel.fetch_message(sent_message.id)

    # Update the table based on feedback
    count_by_emote = {emote.emoji: emote.count for emote in sent_message.reactions}
    update_given_emote_counts(role_id, url, count_by_emote)


bot.run(TOKEN)
