from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from the root repository path
WEB_APP_PATH = Path(__file__).parent.parent.resolve()
load_dotenv(WEB_APP_PATH.joinpath(".env").as_posix())


intents = discord.Intents.default()
intents.members = True
intents.typing = False
bot = commands.Bot(intents=intents, command_prefix="['/tsuki', '/tk']", help_command=None)
