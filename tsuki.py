import asyncio
import os
from pathlib import Path

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load environment variables from the root repository path
WEB_APP_PATH = Path(__file__).parent.resolve()
load_dotenv(WEB_APP_PATH.joinpath(".env").as_posix())

IS_DEV = os.environ.get("IS_DEV", "false") == "true"

from src.birthday_feed import update_birthday_feeds

# Local imports after dotenv to ensure environment variables are available
from src.config.constants import REDDIT_FEED_WINDOW, REPORT_EMOTE, TSUKI_HARAM_HUG, TSUKI_NOM, UPVOTE_EMOTE
from src.content_update import run_content_links_update
from src.db.birthday_feed import set_birthday_feed, unset_birthday_feeds
from src.db.guild_settings import get_min_age, set_min_age
from src.db.reddit_feeds import get_subscriptions, set_reddit_feed, unset_feeds
from src.db.stats import add_stat_count
from src.db.utils import get_closest_roles, get_latest_links_for_roles, get_random_link_for_each_role, get_random_roles
from src.reaction.gather import gather_reactions
from src.reddit_feeds import update_reddit_feeds

TOKEN = os.environ.get("TOKEN")


class TsukiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents, command_prefix="['/tsuki', '/tk', '!']", help_command=None)
        self.custom_event_queue = asyncio.Queue()
        self.active_commands: dict[int, dict[str, list[asyncio.Task]]] = {}

    async def setup_hook(self):
        self.tree.add_command(Admin())
        self.tree.add_command(BirthdayFeed())
        self.tree.add_command(RedditFeed())
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


bot = TsukiBot()


@tasks.loop(seconds=60 * 60 * 12)
async def update_content_loop():
    try:
        await run_content_links_update()
    except Exception as e:
        print(f"Error with content update:\n{str(e)}")


@tasks.loop(seconds=REDDIT_FEED_WINDOW)
async def update_reddit_feeds_loop():
    try:
        await update_reddit_feeds(bot=bot, lookback_secs=REDDIT_FEED_WINDOW)
    except Exception as e:
        print(f"Error with reddit update:\n{str(e)}")


@tasks.loop(seconds=60 * 5)
async def update_birthday_feeds_loop():
    try:
        await update_birthday_feeds(bot=bot)
    except Exception as e:
        print(f"Error with birthday update:\n{str(e)}")


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
        try:
            print("Server name:", server.name, "num of members:", server.member_count)
        except Exception as e:
            print("Could not get server info for:", server.name, str(e))

    if not IS_DEV:
        update_content_loop.start()
        update_reddit_feeds_loop.start()
        update_birthday_feeds_loop.start()


@bot.tree.command(name="feed", description="Get random kpop content using idol or group name.")
@discord.app_commands.describe(query="Idols and groups you want to include. Use `r` or `random` for random idol.")
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

    role_ids_and_urls = get_random_link_for_each_role(role_ids, min_age)
    if not role_ids_and_urls:
        text = f"Could not find a content link for role id `{role_ids[0]}` given query `{query if query else 'random'}`. This message will disappear in 30s."
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return

    # Send the message and get the sent message
    await interaction.response.send_message(role_ids_and_urls[0][1])
    sent_message = await interaction.original_response()

    # React to the sent message with feedback emotes
    emotes = [UPVOTE_EMOTE, REPORT_EMOTE]
    for emote in emotes:
        await sent_message.add_reaction(emote)

    # Count emotes and update database
    sent_message = await interaction.channel.fetch_message(sent_message.id)
    await gather_reactions(message=sent_message, url=role_ids_and_urls[0][1], role_id=role_ids_and_urls[0][0])

    add_stat_count("feed")


@bot.tree.command(name="latest", description="Get latest kpop content using idol or group name.")
@discord.app_commands.describe(
    query="Idols and groups you want to include. Use `a` or `all` for all idols.",
    num_images="Number of images to display. Defaults to 5. Max of 20.",
    skip="Number of images to skip from the beginning. Defaults to 0.",
)
async def latest(interaction: discord.Interaction, query: str | None = None, num_images: int = 5, skip: int = 0):

    if num_images > 20:
        await interaction.response.send_message("Cannot send more than 20 links at a time.", ephemeral=True)
        return

    min_age = get_min_age(interaction.guild_id)
    if query in [None, "a", "all"]:
        role_ids_and_urls = get_latest_links_for_roles(num_links=num_images, skip=skip, min_age=min_age)
    else:
        role_ids = get_closest_roles(query, min_age, count=num_images)
        if not role_ids:
            text = f"Could not find a role for `{query if query else 'random'}`. This message will disappear in 30s."
            print(text)
            await interaction.response.send_message(text, delete_after=30)
            return
        role_ids_and_urls = get_latest_links_for_roles(
            num_links=num_images, skip=skip, min_age=min_age, role_ids=role_ids
        )

    if not role_ids_and_urls:
        await interaction.response.send_message("Could not find any content with these inputs.", ephemeral=True)
        return

    text = f"Fetched latest `{len(role_ids_and_urls)}` images of `{query if query else 'all'}` after skipping first `{skip}` {TSUKI_NOM}"
    try:
        await interaction.response.send_message(content=text)
    except Exception as e:
        print(e)
        return

    message = await interaction.original_response()
    tasks: list[asyncio.Task] = []
    for role_id, url in role_ids_and_urls:
        await asyncio.shield(perform_autofeed_critical_operations(message, url, role_id, tasks))
        if url != role_ids_and_urls[-1][1]:
            await asyncio.sleep(4)

    await asyncio.shield(asyncio.gather(*tasks))
    add_stat_count("latest")


@bot.tree.command(
    name="autofeed",
    description="Feast on kpop content automatically",
)
@discord.app_commands.describe(
    query="Idols and groups you want to include, 'r' or 'random' to be suprised",
    interval="Seconds between posts (default:20, min:2, max:24 hours)",
    count="Number of posts (default:5, max:120)",
)
@discord.app_commands.default_permissions(manage_guild=True)
@discord.app_commands.guild_only()
async def autofeed(interaction: discord.Interaction, query: str | None = None, interval: int = 20, count: int = 5):
    if interval < 2 or interval > 60 * 60 * 24:
        await interaction.response.send_message(
            f"Interval must be between 2 seconds and 24 hours ({60 * 60 * 24}).", ephemeral=True
        )
        return
    if count > 120:
        await interaction.response.send_message("Count cannot be more than 120", ephemeral=True)
        return
    guild_id = interaction.guild_id
    command_name = "autofeed"
    task = asyncio.create_task(autofeed_command(interaction, query, interval, count))
    if guild_id not in bot.active_commands:
        bot.active_commands[guild_id] = {}
    if command_name not in bot.active_commands[guild_id]:
        bot.active_commands[guild_id][command_name] = []
    bot.active_commands[guild_id][command_name].append(task)

    try:
        await task
    finally:
        bot.active_commands[guild_id][command_name].remove(task)
        add_stat_count("autofeed")


async def autofeed_command(interaction: discord.Interaction, query: str | None, interval: int, count: int):
    await interaction.response.defer(thinking=True)
    min_age = get_min_age(interaction.guild_id)
    if query in [None, "r", "random"]:
        role_ids = get_random_roles(count, min_age)
    else:
        role_ids = get_closest_roles(query, min_age, count)

    if not role_ids:
        text = f"Could not find a role for `{query if query else 'random'}`. This message will disappear in 30s."
        print(text)
        message = await interaction.followup.send(content=text, wait=True)
        await message.delete(delay=30)
        return

    # Corrects role_ids to be the length of count if it was too short
    if role_ids and len(role_ids) < count:
        temp = len(role_ids)
        temp = count // temp + 1
        role_ids = (role_ids * temp)[:count]

    role_ids_and_urls = get_random_link_for_each_role(role_ids=role_ids, min_age=min_age)

    # One retry attempt incase a role had a full recently sent queue
    if not role_ids_and_urls or len(role_ids_and_urls) != count:
        role_ids_and_urls = get_random_link_for_each_role(role_ids=role_ids, min_age=min_age)

    # Proceed only if we got more than half of the count urls
    if not role_ids_and_urls or len(role_ids_and_urls) < count // 2:
        text = "Could not find enough pieces of content"
        print(text)
        message = await interaction.followup.send(content=text, wait=True)
        await message.delete(delay=30)
        return

    text = (
        f"Starting feed of `{query if query else 'random'}`!\n"
        + f"Found `{len(role_ids_and_urls)}` ingredient(s) serving every `{interval}` seconds.\n"
        + f"We hope you enjoy your meal {TSUKI_NOM}"
    )
    try:
        await interaction.followup.send(content=text)
    except Exception as e:
        print(e)
        return

    message = await interaction.original_response()

    text = []
    tasks: list[asyncio.Task] = []
    try:
        for role_id, url in role_ids_and_urls:
            await asyncio.shield(perform_autofeed_critical_operations(message, url, role_id, tasks))
            if url != role_ids_and_urls[-1][1]:
                await asyncio.sleep(interval)

    except asyncio.CancelledError:
        text.append("An admin has cancelled this autofeed session.")
    finally:
        text.append(f"Thank you for choosing Fukutomi Diner {TSUKI_HARAM_HUG}")
        await message.reply(" ".join(text))
        await asyncio.shield(asyncio.gather(*tasks))


async def perform_autofeed_critical_operations(
    message: discord.Message, url: str, role_id: str, tasks: list[asyncio.Task]
):
    message = await message.reply(content=url)

    emotes = [UPVOTE_EMOTE, REPORT_EMOTE]
    for emote in emotes:
        await message.add_reaction(emote)

    reaction_gathering_task = asyncio.create_task(gather_reactions(message, url, role_id))
    tasks.append(reaction_gathering_task)


@discord.app_commands.default_permissions(manage_messages=True)
@discord.app_commands.guild_only()
class RedditFeed(discord.app_commands.Group):
    def __init__(self):
        super().__init__(name="reddit_feed", description="Commands for configuring reddit feed.")
        return

    @discord.app_commands.command(
        name="set_feed",
        description="Set a channel to receive updates from a subreddit.",
    )
    @discord.app_commands.describe(
        channel="Channel to receive updates from reddit",
        subreddit="Name of subreddit, defaults to `kpopfap`. Do not include `r/`.",
    )
    async def set_feed(
        self, interaction: discord.Interaction, channel: discord.TextChannel, subreddit: str = "kpopfap"
    ):
        try:
            assert interaction.guild_id is not None
            set_reddit_feed(interaction.guild_id, channel.id, subreddit)
            await interaction.response.send_message(
                f"Channel `{channel.name}` is set to recieve updates from `r/{subreddit}`."
            )
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to set channel: {e}", ephemeral=True)
        add_stat_count("reddit_set_feed")

    @discord.app_commands.command(name="list_feeds", description="List the existing subscriptions for this server.")
    async def list_feeds(self, interaction: discord.Interaction):
        try:
            assert interaction.guild_id is not None
            subs = get_subscriptions(interaction.guild_id)
            if not subs:
                await interaction.response.send_message("No reddit feeds for this server.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Subscriptions of channel and subreddit: `{str(subs)}`")
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to get server subscriptions: {e}", ephemeral=True)
        add_stat_count("reddit_list_feeds")

    @discord.app_commands.command(name="unset_feeds", description="Unset all reddit feeds for this server.")
    async def unset_feeds(self, interaction: discord.Interaction):
        try:
            assert interaction.guild_id is not None
            unset_feeds(interaction.guild_id)
            await interaction.response.send_message("Unset all reddits feed for this server.")
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to unset feeds: {e}", ephemeral=True)
        add_stat_count("reddit_unset_feeds")


@discord.app_commands.default_permissions(manage_messages=True)
@discord.app_commands.guild_only()
class BirthdayFeed(discord.app_commands.Group):
    def __init__(self):
        super().__init__(name="birthday_feed", description="Commands for configuring birthday feed.")
        return

    @discord.app_commands.command(
        name="set_feed",
        description="Set a channel to receive birthday messages.",
    )
    @discord.app_commands.describe(channel="Channel to receive birthday updates")
    async def set_feed(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            assert interaction.guild_id is not None
            set_birthday_feed(interaction.guild_id, channel.id)
            await interaction.response.send_message(f"Channel `{channel.name}` is set to recieve birthday updates.")
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to set channel: {e}", ephemeral=True)
        add_stat_count("birthday_set_feed")

    @discord.app_commands.command(name="unset_feeds", description="Unset all birthday feeds for this server.")
    async def unset_feeds(self, interaction: discord.Interaction):
        try:
            assert interaction.guild_id is not None
            unset_birthday_feeds(interaction.guild_id)
            await interaction.response.send_message("Unset all birthday feeds for this server.")
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to unset feeds: {e}", ephemeral=True)
        add_stat_count("birthday_unset_feed")


@discord.app_commands.default_permissions(manage_guild=True)
@discord.app_commands.guild_only()
class Admin(discord.app_commands.Group):
    def __init__(self):
        super().__init__(name="admin", description="Commands for managing TsukiBot")
        return

    @discord.app_commands.command(
        name="cancel_all_autofeeds",
        description="Terminate all running autofeed commands",
    )
    async def cancel_all_autofeeds(self, interaction: discord.Interaction):
        await bot.custom_event_queue.put(
            {"type": "cancel_command", "guild_id": interaction.guild_id, "command_name": "autofeed"}
        )
        text = "Cancelling all autofeed commands"
        print(f"Guild: {interaction.guild_id} Request: {text}")
        await interaction.response.send_message(text)
        add_stat_count("cancel_all_autofeeds")

    @discord.app_commands.command(
        name="set_age_limit", description="Set the minimum age of idol at content upload time."
    )
    @discord.app_commands.describe(min_age="Minimum age. E.g. `18 year 6 month`, `19 year 3 week`")
    async def set_age_limit(self, interaction: discord.Interaction, min_age: str):
        assert interaction.guild_id is not None
        # Sanitize the input a bit to make it more lenient
        min_age = min_age.lower()
        for plural, singular in {"years": "year", "months": "month", "weeks": "week", "days": "day"}.items():
            min_age = min_age.replace(plural, singular)
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
        add_stat_count("set_age_limit")


bot.run(TOKEN)
