import asyncio
import os
from pathlib import Path

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load environment variables from the root repository path
WEB_APP_PATH = Path(__file__).parent.resolve()
load_dotenv(WEB_APP_PATH.joinpath(".env").as_posix())


# Local imports after dotenv to ensure environment variables are available
from src.config.constants import REACT_WAIT_SEC, REPORT_EMOTE, UPVOTE_EMOTE
from src.content_update import run_content_links_update
from src.db.guild_settings import get_min_age, set_min_age
from src.db.utils import get_closest_roles, get_random_link_for_each_role, get_random_roles, update_given_emote_counts

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(intents=intents, command_prefix="['/tsuki', '/tk', '/feed', '!']", help_command=None)


@tasks.loop(seconds=60 * 60 * 24)
async def update_content_loop():
    await run_content_links_update()


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
        print("Server name:", server.name, ", owner:", server.owner.name, "num of members:", server.member_count)

    # update_content_loop.start()


@bot.tree.command(
    name="set_age_limit", description="Set the minimum age of idol at content upload time. E.g. `19 year 1 month`"
)
@discord.app_commands.default_permissions(manage_guild=True)
async def set_age_limit(interaction: discord.Interaction, min_age: str):
    assert interaction.guild_id is not None
    try:
        if "year" not in min_age or int(min_age.split("year")[0]) < 18:
            await interaction.response.send_message(
                "Min age should be at least 18, e.g. `18 year 1 month`", ephemeral=True
            )

        else:
            set_min_age(interaction.guild_id, min_age)
            await interaction.response.send_message(
                f"Min age has been successfully set to `{min_age}`.", ephemeral=True
            )

    except Exception as e:
        print(f"Guild setting failed for guild {interaction.guild_id}: {e}")
        await interaction.response.send_message(
            "Min age was not poorly formatted. Should be in the format `22 year 2 month 2 week`", ephemeral=True
        )
        raise e


@bot.tree.command(
    name="feed", description="Get kpop content using idol or group name. Use `r` or `random` for random idol."
)
async def feed(interaction: discord.Interaction, query: str | None = None):

    min_age = get_min_age(interaction.guild_id)
    if query in [None, "r", "random"]:
        role_ids = get_random_roles(1, min_age)
    else:
        role_ids = get_closest_roles(query, min_age)

    if not role_ids:
        text = f"Could not find a role for `{query if query else 'random'}`. This message will disappear in 30s."
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return

    urls = get_random_link_for_each_role(role_ids, min_age)
    if not urls:
        text = f"Could not find a content link for role id `{role_ids[0]}` given query `{query if query else 'random'}`. This message will disappear in 30s."
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return

    # Send the message and get the sent message
    await interaction.response.send_message(urls[0])
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
    update_given_emote_counts(role_ids[0], urls[0], count_by_emote)


bot.run(TOKEN)
