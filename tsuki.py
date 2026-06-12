import asyncio
import os
import random
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
from src.config.constants import (
    REDDIT_FEED_WINDOW,
    REPORT_EMOTE,
    TSUKI_HARAM_HUG,
    TSUKI_NOM,
    UPVOTE_EMOTE,
)
from src.content_update import run_content_links_update
from src.db.bias_rater import (
    cleanup_accumulating_tables,
    create_weekly_leaderboard_snapshots,
    get_global_group_leaderboard,
    get_global_leaderboard,
    get_guild_group_leaderboard,
    get_guild_leaderboard,
    get_personal_group_leaderboard,
    get_personal_leaderboard,
    has_completed_daily,
)
from src.db.birthday_feed import set_birthday_feed, unset_birthday_feeds
from src.db.guild_settings import get_min_age, set_min_age
from src.db.reddit_feeds import get_subscriptions, set_reddit_feed, unset_feeds
from src.db.stats import add_stat_count
from src.db.utils import (
    get_closest_roles,
    get_latest_links_for_roles,
    get_random_link_for_each_role,
    get_random_roles,
)
from src.discord_ui.bias_rater import (
    LEADERBOARD_MAX_ENTRIES,
    LEADERBOARD_PAGE_SIZE,
    LeaderboardView,
    VoteView,
    build_group_leaderboard_embeds,
    build_leaderboard_embeds,
)
from src.llm_chat import ChatMsg, generate_chat_response
from src.reaction.gather import gather_dead_link, gather_reactions
from src.reddit_feeds import update_reddit_feeds

TOKEN = os.environ.get("TOKEN")
OWNER_USER_ID = 1298088341241335841
OWNER_WHISPER_PREFIX = "whisper "


class TsukiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            intents=intents, command_prefix="['/tsuki', '/tk', '!']", help_command=None
        )
        self.custom_event_queue = asyncio.Queue()
        self.active_commands: dict[int, dict[str, list[asyncio.Task]]] = {}

    async def setup_hook(self):
        self.tree.add_command(Admin())
        self.tree.add_command(BirthdayFeed())
        self.tree.add_command(RedditFeed())
        self.tree.add_command(BiasRater())
        asyncio.create_task(self.custom_event_handler())

    async def custom_event_handler(self):
        while True:
            event = await self.custom_event_queue.get()
            if event["type"] == "cancel_command":
                guild_id = event["guild_id"]
                command_name = event["command_name"]
                if (
                    guild_id in self.active_commands
                    and command_name in self.active_commands[guild_id]
                ):
                    command_tasks = self.active_commands[guild_id][command_name]
                    for command_task in command_tasks:
                        command_task.cancel()


bot = TsukiBot()


def start_loop_once(loop: tasks.Loop) -> None:
    if not loop.is_running():
        loop.start()


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


@tasks.loop(seconds=60 * 60 * 6)
async def update_bias_leaderboard_snapshots_loop():
    try:
        inserted = await asyncio.to_thread(create_weekly_leaderboard_snapshots)
        if any(inserted.values()):
            print(f"Created bias leaderboard snapshots: {inserted}")
    except Exception as e:
        print(f"Error with bias leaderboard snapshots:\n{str(e)}")


@tasks.loop(seconds=60 * 60 * 24)
async def cleanup_accumulating_tables_loop():
    try:
        deleted = await asyncio.to_thread(cleanup_accumulating_tables)
        if any(deleted.values()):
            print(f"Cleaned up accumulating tables: {deleted}")
    except Exception as e:
        print(f"Error with accumulating table cleanup:\n{str(e)}")


@bot.event
async def on_ready():
    try:
        print(f"Signed in as {bot.user}")
        await bot.tree.sync()
        print("Successfully synced commands.")
    except Exception as e:
        print(e)

    print(f"Currently in {len(bot.guilds)} servers:")
    for server in bot.guilds:
        try:
            print(
                "Server name:",
                server.name,
                ", ID:",
                server.id,
                ", num of members:",
                server.member_count,
            )
        except Exception as e:
            print("Could not get server info for:", server.name, str(e))

    if not IS_DEV:
        start_loop_once(update_content_loop)
        start_loop_once(update_reddit_feeds_loop)
        start_loop_once(update_birthday_feeds_loop)
        start_loop_once(update_bias_leaderboard_snapshots_loop)
        start_loop_once(cleanup_accumulating_tables_loop)


@bot.tree.command(name="feed", description="Get random kpop content using idol or group name.")
@discord.app_commands.describe(
    query="Idols and groups you want to include. Use `r` or `random` for random idol."
)
async def feed(interaction: discord.Interaction, query: str | None = None):
    if not await asyncio.to_thread(has_completed_daily, interaction.user.id):
        await interaction.response.send_message(
            f"Complete today's `/bias daily` before using feed! {TSUKI_NOM}",
            ephemeral=True,
        )
        return
    min_age = await asyncio.to_thread(get_min_age, interaction.guild_id)
    if query in [None, "r", "random"]:
        role_ids = await asyncio.to_thread(get_random_roles, 1, min_age)
    else:
        role_ids = await asyncio.to_thread(get_closest_roles, query, min_age)

    if not role_ids:
        text = f"Could not find a role for `{query if query else 'random'}`. This message will disappear in 30s."
        print(text)
        await interaction.response.send_message(text, delete_after=30)
        return

    role_ids_and_urls = await asyncio.to_thread(get_random_link_for_each_role, role_ids, min_age)
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
    await gather_reactions(
        message=sent_message,
        url=role_ids_and_urls[0][1],
        role_id=role_ids_and_urls[0][0],
    )

    await asyncio.to_thread(add_stat_count, "feed")


@bot.tree.command(name="latest", description="Get latest kpop content using idol or group name.")
@discord.app_commands.describe(
    query="Idols and groups you want to include. Use `a` or `all` for all idols.",
    num_images="Number of images to display. Defaults to 5. Max of 20.",
    skip="Number of images to skip from the beginning. Defaults to 0.",
)
async def latest(
    interaction: discord.Interaction,
    query: str | None = None,
    num_images: int = 5,
    skip: int = 0,
):
    if not await asyncio.to_thread(has_completed_daily, interaction.user.id):
        await interaction.response.send_message(
            f"Complete today's `/bias daily` before using latest! {TSUKI_NOM}",
            ephemeral=True,
        )
        return
    if num_images > 20:
        await interaction.response.send_message(
            "Cannot send more than 20 links at a time.", ephemeral=True
        )
        return

    min_age = await asyncio.to_thread(get_min_age, interaction.guild_id)
    if query in [None, "a", "all"]:
        role_ids_and_urls = await asyncio.to_thread(
            get_latest_links_for_roles, num_links=num_images, skip=skip, min_age=min_age
        )
    else:
        role_ids = await asyncio.to_thread(get_closest_roles, query, min_age, count=num_images)
        if not role_ids:
            text = f"Could not find a role for `{query if query else 'random'}`. This message will disappear in 30s."
            print(text)
            await interaction.response.send_message(text, delete_after=30)
            return
        role_ids_and_urls = await asyncio.to_thread(
            get_latest_links_for_roles,
            num_links=num_images,
            skip=skip,
            min_age=min_age,
            role_ids=role_ids,
        )

    if not role_ids_and_urls:
        await interaction.response.send_message(
            "Could not find any content with these inputs.", ephemeral=True
        )
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
    await asyncio.to_thread(add_stat_count, "latest")


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
async def autofeed(
    interaction: discord.Interaction,
    query: str | None = None,
    interval: int = 20,
    count: int = 5,
):
    if not await asyncio.to_thread(has_completed_daily, interaction.user.id):
        await interaction.response.send_message(
            f"Complete today's `/bias daily` before using autofeed! {TSUKI_NOM}",
            ephemeral=True,
        )
        return
    if interval < 2 or interval > 60 * 60 * 24:
        await interaction.response.send_message(
            f"Interval must be between 2 seconds and 24 hours ({60 * 60 * 24}).",
            ephemeral=True,
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
        await asyncio.to_thread(add_stat_count, "autofeed")


async def autofeed_command(
    interaction: discord.Interaction, query: str | None, interval: int, count: int
):
    await interaction.response.defer(thinking=True)
    min_age = await asyncio.to_thread(get_min_age, interaction.guild_id)
    if query in [None, "r", "random"]:
        role_ids = await asyncio.to_thread(get_random_roles, count, min_age)
    else:
        role_ids = await asyncio.to_thread(get_closest_roles, query, min_age, count)

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

    role_ids_and_urls = await asyncio.to_thread(
        get_random_link_for_each_role, role_ids=role_ids, min_age=min_age
    )

    # One retry attempt incase a role had a full recently sent queue
    if not role_ids_and_urls or len(role_ids_and_urls) != count:
        role_ids_and_urls = await asyncio.to_thread(
            get_random_link_for_each_role, role_ids=role_ids, min_age=min_age
        )

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
        text.append(f"Thank you for choosing HanniBot {TSUKI_HARAM_HUG}")
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


async def bias_autofeed_command(
    interaction: discord.Interaction, scope: str, interval: int, count: int
):
    await interaction.response.defer(thinking=True)
    min_age = await asyncio.to_thread(get_min_age, interaction.guild_id)

    if scope == "global":
        tops = await asyncio.to_thread(get_global_leaderboard, 15)
    elif scope == "server":
        tops = await asyncio.to_thread(get_guild_leaderboard, interaction.guild_id, 15)
    else:
        tops = await asyncio.to_thread(get_personal_leaderboard, interaction.user.id, 15)

    if not tops.entries:
        text = f"Could not find any {scope} bias rankings. Try voting with `/bias vote` first!"
        print(text)
        message = await interaction.followup.send(content=text, wait=True)
        await message.delete(delay=30)
        return

    # Weightings for ranks 1-15
    full_weights = [100, 70, 60, 50, 40, 30, 20, 15, 15, 10, 5, 2, 2, 2, 2]
    weights = full_weights[: len(tops.entries)]

    top_roles = [entry.role_id for entry in tops.entries]

    # Pick randomly with weights and replacement
    role_ids = random.choices(top_roles, weights=weights, k=count)

    role_ids_and_urls = await asyncio.to_thread(
        get_random_link_for_each_role, role_ids=role_ids, min_age=min_age
    )

    # One retry attempt incase a role had a full recently sent queue
    if not role_ids_and_urls or len(role_ids_and_urls) != count:
        role_ids_and_urls = await asyncio.to_thread(
            get_random_link_for_each_role, role_ids=role_ids, min_age=min_age
        )

    # Proceed only if we got more than half of the count urls
    if not role_ids_and_urls or len(role_ids_and_urls) < count // 2:
        text = "Could not find enough pieces of content"
        print(text)
        message = await interaction.followup.send(content=text, wait=True)
        await message.delete(delay=30)
        return

    text = (
        f"Starting {scope} bias feed!\n"
        + f"Found `{len(role_ids_and_urls)}` ingredient(s) serving every `{interval}` seconds.\n"
        + f"We hope you enjoy your meal {TSUKI_NOM}"
    )
    try:
        await interaction.followup.send(content=text)
    except Exception as e:
        print(e)
        return

    message = await interaction.original_response()

    text_parts = []
    tasks: list[asyncio.Task] = []
    try:
        for role_id, url in role_ids_and_urls:
            await asyncio.shield(perform_autofeed_critical_operations(message, url, role_id, tasks))
            if url != role_ids_and_urls[-1][1]:
                await asyncio.sleep(interval)

    except asyncio.CancelledError:
        text_parts.append("An admin has cancelled this autofeed session.")
    finally:
        text_parts.append(f"Thank you for choosing HanniBot {TSUKI_HARAM_HUG}")
        await message.reply(" ".join(text_parts))
        await asyncio.shield(asyncio.gather(*tasks))


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
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        subreddit: str = "kpopfap",
    ):
        try:
            assert interaction.guild_id is not None
            await asyncio.to_thread(set_reddit_feed, interaction.guild_id, channel.id, subreddit)
            await interaction.response.send_message(
                f"Channel `{channel.name}` is set to recieve updates from `r/{subreddit}`."
            )
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to set channel: {e}", ephemeral=True)
        await asyncio.to_thread(add_stat_count, "reddit_set_feed")

    @discord.app_commands.command(
        name="list_feeds",
        description="List the existing subscriptions for this server.",
    )
    async def list_feeds(self, interaction: discord.Interaction):
        try:
            assert interaction.guild_id is not None
            subs = await asyncio.to_thread(get_subscriptions, interaction.guild_id)
            if not subs:
                await interaction.response.send_message(
                    "No reddit feeds for this server.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Subscriptions of channel and subreddit: `{str(subs)}`"
                )
        except Exception as e:
            print(e)
            await interaction.response.send_message(
                f"Failed to get server subscriptions: {e}", ephemeral=True
            )
        await asyncio.to_thread(add_stat_count, "reddit_list_feeds")

    @discord.app_commands.command(
        name="unset_feeds", description="Unset all reddit feeds for this server."
    )
    async def unset_feeds(self, interaction: discord.Interaction):
        try:
            assert interaction.guild_id is not None
            await asyncio.to_thread(unset_feeds, interaction.guild_id)
            await interaction.response.send_message("Unset all reddits feed for this server.")
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to unset feeds: {e}", ephemeral=True)
        await asyncio.to_thread(add_stat_count, "reddit_unset_feeds")


@discord.app_commands.default_permissions(manage_messages=True)
@discord.app_commands.guild_only()
class BirthdayFeed(discord.app_commands.Group):
    def __init__(self):
        super().__init__(
            name="birthday_feed", description="Commands for configuring birthday feed."
        )
        return

    @discord.app_commands.command(
        name="set_feed",
        description="Set a channel to receive birthday messages.",
    )
    @discord.app_commands.describe(channel="Channel to receive birthday updates")
    async def set_feed(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            assert interaction.guild_id is not None
            await asyncio.to_thread(set_birthday_feed, interaction.guild_id, channel.id)
            await interaction.response.send_message(
                f"Channel `{channel.name}` is set to recieve birthday updates."
            )
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to set channel: {e}", ephemeral=True)
        await asyncio.to_thread(add_stat_count, "birthday_set_feed")

    @discord.app_commands.command(
        name="unset_feeds", description="Unset all birthday feeds for this server."
    )
    async def unset_feeds(self, interaction: discord.Interaction):
        try:
            assert interaction.guild_id is not None
            await asyncio.to_thread(unset_birthday_feeds, interaction.guild_id)
            await interaction.response.send_message("Unset all birthday feeds for this server.")
        except Exception as e:
            print(e)
            await interaction.response.send_message(f"Failed to unset feeds: {e}", ephemeral=True)
        await asyncio.to_thread(add_stat_count, "birthday_unset_feed")


@discord.app_commands.default_permissions(manage_guild=True)
@discord.app_commands.guild_only()
class Admin(discord.app_commands.Group):
    def __init__(self):
        super().__init__(name="admin", description="Commands for managing HanniBot")
        return

    @discord.app_commands.command(
        name="cancel_all_autofeeds",
        description="Terminate all running autofeed commands",
    )
    async def cancel_all_autofeeds(self, interaction: discord.Interaction):
        await bot.custom_event_queue.put(
            {
                "type": "cancel_command",
                "guild_id": interaction.guild_id,
                "command_name": "autofeed",
            }
        )
        text = "Cancelling all autofeed commands"
        print(f"Guild: {interaction.guild_id} Request: {text}")
        await interaction.response.send_message(text)
        await asyncio.to_thread(add_stat_count, "cancel_all_autofeeds")

    @discord.app_commands.command(
        name="set_age_limit",
        description="Set the minimum age of idol at content upload time.",
    )
    @discord.app_commands.describe(min_age="Minimum age. E.g. `18 year 6 month`, `19 year 3 week`")
    async def set_age_limit(self, interaction: discord.Interaction, min_age: str):
        assert interaction.guild_id is not None
        # Sanitize the input a bit to make it more lenient
        min_age = min_age.lower()
        for plural, singular in {
            "years": "year",
            "months": "month",
            "weeks": "week",
            "days": "day",
        }.items():
            min_age = min_age.replace(plural, singular)
        try:
            if "year" not in min_age or int(min_age.split("year")[0]) < 18:
                await interaction.response.send_message(
                    "Min age should be at least 18, e.g. `18 year 1 month`",
                    ephemeral=True,
                )

            else:
                await asyncio.to_thread(set_min_age, interaction.guild_id, min_age)
                await interaction.response.send_message(
                    f"Min age has been successfully set to `{min_age}`.", ephemeral=True
                )

        except Exception as e:
            print(f"Guild setting failed for guild {interaction.guild_id}: {e}")
            await interaction.response.send_message(
                "Min age was not poorly formatted. Should be in the format `22 year 2 month 2 week`",
                ephemeral=True,
            )
        await asyncio.to_thread(add_stat_count, "set_age_limit")


@discord.app_commands.guild_only()
class BiasRater(discord.app_commands.Group):
    def __init__(self):
        super().__init__(name="bias", description="Commands for head-to-head idol voting")

    @discord.app_commands.command(name="vote", description="Vote head-to-head for idols")
    async def vote(self, interaction: discord.Interaction):
        # Ack immediately so Discord's 3s interaction deadline doesn't expire
        # while VoteView.create does its DB round-trip on a possibly-cold connection.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            view = await VoteView.create(
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
            )
            view.interaction = interaction
            await interaction.edit_original_response(embeds=view.embeds, view=view)
        except Exception as e:
            await interaction.edit_original_response(content=f"Could not start voting: {str(e)}")
        await asyncio.to_thread(add_stat_count, "bias_vote")

    @discord.app_commands.command(
        name="daily",
        description="Today's 8-idol bracket challenge (same set for everyone, once per day)",
    )
    async def daily(self, interaction: discord.Interaction):
        if await asyncio.to_thread(has_completed_daily, interaction.user.id):
            await interaction.response.send_message(
                "You've already completed today's daily bracket! Come back tomorrow.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            view = await VoteView.create_daily(
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
            )
            view.interaction = interaction
            await interaction.edit_original_response(embeds=view.embeds, view=view)
        except Exception as e:
            await interaction.edit_original_response(content=f"Could not start daily: {str(e)}")
        await asyncio.to_thread(add_stat_count, "bias_daily")

    @discord.app_commands.command(name="leaderboard", description="Show ELO leaderboard")
    @discord.app_commands.describe(
        scope="global, server, or personal",
        user="User whose personal leaderboard to show; only used with personal scope",
    )
    @discord.app_commands.choices(
        scope=[
            discord.app_commands.Choice(name="Global", value="global"),
            discord.app_commands.Choice(name="Server", value="server"),
            discord.app_commands.Choice(name="Personal", value="personal"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        scope: str = "personal",
        user: discord.User | None = None,
    ):
        # Ack first; the DB query below can exceed Discord's 3s deadline on a cold connection.
        await interaction.response.defer()
        if scope == "global":
            tops = await asyncio.to_thread(get_global_leaderboard, LEADERBOARD_MAX_ENTRIES)
            title = "Global Idol Leaderboard"
        elif scope == "server":
            tops = await asyncio.to_thread(
                get_guild_leaderboard, interaction.guild_id, LEADERBOARD_MAX_ENTRIES
            )
            title = f"Server Leaderboard for {interaction.guild.name}"
        else:
            target_user = user or interaction.user
            tops = await asyncio.to_thread(
                get_personal_leaderboard, target_user.id, LEADERBOARD_MAX_ENTRIES
            )
            title = f"Personal Leaderboard for {target_user.display_name}"

        if not tops.entries:
            await interaction.edit_original_response(content="No votes recorded yet!")
            return

        view = LeaderboardView(title, tops) if len(tops.entries) > LEADERBOARD_PAGE_SIZE else None
        embeds = view.embeds if view else build_leaderboard_embeds(title, tops)
        message = await interaction.edit_original_response(embeds=embeds, view=view)
        if view:
            view.message = message
        await asyncio.to_thread(add_stat_count, "bias_leaderboard")

    @discord.app_commands.command(name="groups", description="Show group ELO leaderboard")
    @discord.app_commands.describe(scope="global, server, or personal")
    @discord.app_commands.choices(
        scope=[
            discord.app_commands.Choice(name="Global", value="global"),
            discord.app_commands.Choice(name="Server", value="server"),
            discord.app_commands.Choice(name="Personal", value="personal"),
        ]
    )
    async def groups(self, interaction: discord.Interaction, scope: str = "personal"):
        # Ack first; the DB query below can exceed Discord's 3s deadline on a cold connection.
        await interaction.response.defer()
        if scope == "global":
            tops = await asyncio.to_thread(get_global_group_leaderboard)
            title = "Global Group Leaderboard"
        elif scope == "server":
            tops = await asyncio.to_thread(get_guild_group_leaderboard, interaction.guild_id)
            title = f"Server Group Leaderboard for {interaction.guild.name}"
        else:
            tops = await asyncio.to_thread(get_personal_group_leaderboard, interaction.user.id)
            title = f"Personal Group Leaderboard for {interaction.user.display_name}"

        if not tops.entries:
            await interaction.edit_original_response(content="No votes recorded yet!")
            return

        embeds = build_group_leaderboard_embeds(title, tops)
        await interaction.edit_original_response(embeds=embeds)
        await asyncio.to_thread(add_stat_count, "bias_groups")

    @discord.app_commands.command(
        name="autofeed",
        description="Feast on kpop content automatically based on your idol bias rankings",
    )
    @discord.app_commands.describe(
        scope="Rankings to base feed off of: personal, server, or global (default: personal)",
        interval="Seconds between posts (default:20, min:2, max:24 hours)",
        count="Number of posts (default:5, max:120)",
    )
    @discord.app_commands.choices(
        scope=[
            discord.app_commands.Choice(name="Personal", value="personal"),
            discord.app_commands.Choice(name="Server", value="server"),
            discord.app_commands.Choice(name="Global", value="global"),
        ]
    )
    async def autofeed(
        self,
        interaction: discord.Interaction,
        scope: str = "personal",
        interval: int = 20,
        count: int = 5,
    ):
        if not await asyncio.to_thread(has_completed_daily, interaction.user.id):
            await interaction.response.send_message(
                f"Complete today's `/bias daily` before using autofeed! {TSUKI_NOM}",
                ephemeral=True,
            )
            return
        if interval < 2 or interval > 60 * 60 * 24:
            await interaction.response.send_message(
                f"Interval must be between 2 seconds and 24 hours ({60 * 60 * 24}).",
                ephemeral=True,
            )
            return
        if count > 120:
            await interaction.response.send_message("Count cannot be more than 120", ephemeral=True)
            return
        guild_id = interaction.guild_id
        command_name = "autofeed"  # using autofeed command name so /admin cancel works on this too
        task = asyncio.create_task(bias_autofeed_command(interaction, scope, interval, count))
        if guild_id not in bot.active_commands:
            bot.active_commands[guild_id] = {}
        if command_name not in bot.active_commands[guild_id]:
            bot.active_commands[guild_id][command_name] = []
        bot.active_commands[guild_id][command_name].append(task)

        try:
            await task
        finally:
            bot.active_commands[guild_id][command_name].remove(task)
            await asyncio.to_thread(add_stat_count, "bias_autofeed")


async def handle_owner_whisper(message: discord.Message) -> bool:
    # Usage: DM the bot with `whisper <channel_id> <message>`.
    if message.author.id != OWNER_USER_ID:
        return False
    if not isinstance(message.channel, discord.DMChannel):
        return False
    if not message.content.startswith(OWNER_WHISPER_PREFIX):
        return False

    command_text = message.content[len(OWNER_WHISPER_PREFIX) :].strip()
    try:
        channel_id_text, whisper_text = command_text.split(maxsplit=1)
        channel_id = int(channel_id_text)
    except ValueError:
        await message.channel.send("Usage: `whisper <channel_id> <message>`")
        return True

    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    except (discord.Forbidden, discord.HTTPException, discord.NotFound):
        await message.channel.send("I could not find or access that channel.")
        return True

    if not isinstance(channel, discord.abc.Messageable):
        await message.channel.send("That target is not a messageable channel.")
        return True

    try:
        sent = await channel.send(
            whisper_text,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )
    except discord.Forbidden:
        await message.channel.send("I do not have permission to send messages there.")
        return True
    except discord.HTTPException as e:
        await message.channel.send(f"Failed to send message: {e}")
        return True

    print(f"Owner whisper sent to channel {channel_id}, message {sent.id}")
    await message.channel.send(f"Sent to <#{channel_id}>.")
    return True


def _to_chat_msg(message: discord.Message, is_trigger: bool = False) -> ChatMsg:
    # Use raw content (not clean_content) so the model sees real `<@id>`
    # mentions and `<:emoji:id>` codes instead of flattened display names.
    return ChatMsg(
        author_name=message.author.display_name,
        author_id=message.author.id,
        is_tsuki=message.author == bot.user,
        content=message.content,
        is_trigger=is_trigger,
    )


async def handle_tsuki_chat(message: discord.Message) -> None:
    channel = message.channel
    try:
        # Only the slow generation step shows the typing indicator. Sends happen
        # after the context closes so "typing..." doesn't linger past the reply.
        async with channel.typing():
            # Recent history (chronological) followed by the triggering message.
            history: list[discord.Message] = []
            async for msg in channel.history(limit=30, before=message):
                history.append(msg)
            history.reverse()
            history.append(message)

            min_age = (
                await asyncio.to_thread(get_min_age, message.guild.id)
                if message.guild
                else "18 year 1 month"
            )

            chat_msgs = [
                _to_chat_msg(msg, is_trigger=(msg is message))
                for msg in history
                if msg.content.strip()
            ]
            result = await generate_chat_response(chat_msgs, min_age)

        await channel.send(
            result.text or "<:hanni_despair:1515066515408425031>",
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
        for url in result.attachments:
            await channel.send(url)

        await asyncio.to_thread(add_stat_count, "llm_response")
    except Exception as e:
        print(f"LLM chat error: {e}")
        await channel.send(
            f"something happened inside me <:hanni_despair:1515066515408425031>\n{e}"
        )


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # Owner whisper handling happens over DM only.
    if isinstance(message.channel, discord.DMChannel):
        await handle_owner_whisper(message)
        return

    # Respond only to an explicit @mention in the message text. raw_mentions is
    # parsed from the content, so it excludes the auto-ping Discord adds when
    # someone merely replies to one of her messages.
    if bot.user is not None and bot.user.id in message.raw_mentions:
        await handle_tsuki_chat(message)


bot.run(TOKEN)
