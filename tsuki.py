import os
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from the root repository path
WEB_APP_PATH = Path(__file__).parent.resolve()
load_dotenv(WEB_APP_PATH.joinpath(".env").as_posix())


# Local imports after dotenv to ensure environment variables are available
from src.db.utils import get_random_link_for_role, find_closest_role

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(intents=intents, command_prefix="['/tsuki', '/tk', '/feed']", help_command=None)


@bot.command()
async def feed(ctx, query: str):
    role_id = find_closest_role(query)
    if not role_id:
        print(f"Could not find a role for '{query}'")

    url = get_random_link_for_role(role_id)
    if not url:
        print(f"Could not find URL for '{role_id}'")

    await ctx.send(url)


bot.run(TOKEN)
