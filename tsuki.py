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
from src.config.constants import REACT_WAIT_SEC, REPORT_EMOTE, UPVOTE_EMOTE, TSUKI_NOM, TSUKI_HARAM_HUG
from src.db.utils import get_closest_roles, get_random_link_for_each_role, get_random_roles, update_given_emote_counts
from src.reaction.gather import gather_reactions

TOKEN = os.environ.get("TOKEN")

class TsukiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents, command_prefix="['/tsuki', '/tk', '!']", help_command=None)
        self.custom_event_queue = asyncio.Queue()
        self.active_commands: dict[int, dict[str, list[asyncio.Task]]] = {}
    
    async def setup_hook(self):
        self.tree.add_command(Admin())
        asyncio.create_task(self.custom_event_handler())
    
    async def custom_event_handler(self):
        while True:
            event = await self.custom_event_queue.get()
            if event["type"] == "cancel_command":
                guild_id = event["guild_id"]
                command_name = event["command_name"]
                if guild_id in self.active_commands and command_name in self.active_commands[guild_id]:
                    command_tasks = self.active_commands[guild_id][command_name]
                    for command_task in command_tasks:
                        command_task.cancel()
                    self.active_commands[guild_id][command_name] = []
    
bot = TsukiBot()

@bot.tree.command(
    name="feed", description="Get kpop content using idol or group name. Use `r` or `random` for random idol."
)
async def feed(interaction: discord.Interaction, query: str | None = None):
    if query in [None, "r", "random"]:
        role_ids = get_random_roles(1)
    else:
        role_ids = get_closest_roles(query)

    if not role_ids:
        text = f"Could not find a role for `{query if query else 'random'}`. This message will disappear in 30s."
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return

    urls = get_random_link_for_each_role(role_ids)
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

@bot.tree.command(name="autofeed", description= "Feast on kpop content, interval for seconds between post, " +
                  "and count for number of posts.")
@discord.app_commands.default_permissions(manage_guild=True)
async def autofeed(interaction: discord.Interaction, query: str | None = None, interval: int = 20, count: int = 5):
    guild_id = interaction.guild_id
    command_name = "autofeed"
    task = asyncio.create_task(autofeed_command(interaction, query, interval, count))
    if guild_id not in bot.active_commands:
        bot.active_commands[guild_id] = {}
    if command_name not in bot.active_commands[guild_id]:
        bot.active_commands[guild_id][command_name] = []
    bot.active_commands[guild_id][command_name].append(task)


async def autofeed_command(interaction: discord.Interaction, query: str | None, interval: int, count: int):
    if query in [None, "r", "random"]:
        role_ids = get_random_roles(count)
    else:
        role_ids = get_closest_roles(query, count)
        temp = len(role_ids)
        temp = count // temp + 1
        role_ids = (role_ids * temp)[:count]
    
    print(role_ids)

    if not role_ids or (len(role_ids) < count and not (query not in [None, "r", "random"] and len(role_ids) == 1)):
        text = f"Could not find enough roles"
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return
    
    urls = get_random_link_for_each_role(role_ids=role_ids)
    print(urls)
    if not urls or len(urls) < count:
        text = f"Could not find {count} pieces of content"
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return
    
    try:
        text = f"Starting feed of `{query if query else 'random'}`! We hope you enjoy your meal {TSUKI_NOM}"
        await interaction.response.send_message(content=text)
    except Exception as e:
        print(e)
        return

    
    message = await interaction.original_response()

    text = []
    tasks = []
    try:
        for url, role_id in zip_longest(urls, role_ids):
            await asyncio.shield(perform_autofeed_critical_opertaions(message, url, role_id, tasks))
            await asyncio.sleep(interval)

        
    except asyncio.CancelledError:
        text.append("An Administator has cancelled this autofeed session.")
        return
    finally:
        text.append(f"Thank you for choosing Fukotomi Diner {TSUKI_HARAM_HUG}")
        await message.reply(" ".join(text))
        await asyncio.shield(asyncio.gather(*tasks))

async def perform_autofeed_critical_opertaions(message: discord.Message, url: str, role_id: int, tasks: list[asyncio.Task]):
    message = await message.reply(content=url)

    emotes = [UPVOTE_EMOTE, REPORT_EMOTE]
    for emote in emotes:
        await message.add_reaction(emote)
    
    reaction_gathering_task = asyncio.create_task(gather_reactions(message, url, role_id))
    tasks.append(reaction_gathering_task)

@discord.app_commands.default_permissions(manage_guild=True)
class Admin(discord.app_commands.Group):
    def __init__(self):
        super().__init__(name="admin", description="Commands for managing TsukiBot")
        return
    
    @discord.app_commands.command(name="cancel_all_autofeeds", description="Terminate all running autofeed commands",)
    async def cancel_all_autofeeds(self, interaction: discord.Interaction):
        await bot.custom_event_queue.put({"type": "cancel_command", "guild_id": interaction.guild_id, "command_name": "autofeed"})
        text = "Cancelling all autofeed commands"
        print(f"Guild: {interaction.guild_id} Request: {text}")
        await interaction.response.send_message(text)


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

bot.run(TOKEN)