from discord.ext import commands

from src.db.birthday_feed import get_birthday_feeds, get_recent_birthdays, get_recent_messages, log_message
from src.db.utils import get_random_link_for_each_role


async def update_birthday_feeds(bot: commands.Bot) -> None:
    print("Starting birthday feeds...")
    # 1. Get all the birthday feeds (guild_id, channel_id)
    birthday_feeds = get_birthday_feeds()

    # 2. Get all the recent birthdays (role_id, member_name, group_name)
    recent_birthdays = get_recent_birthdays()

    # 3. Get all the recent birthday messages (guild_id, channel_id, role_id)
    recent_messages = get_recent_messages()

    # Create a set for quick lookup of recent messages to avoid duplicates
    recent_messages_set = {(guild_id, channel_id, role_id) for guild_id, channel_id, role_id in recent_messages}

    # 4. Iterate through all birthday feeds and send unsent messages
    for guild_id, channel_id in birthday_feeds:
        for role_id, member_name, group_name in recent_birthdays:
            # Check if the message has already been sent
            if (guild_id, channel_id, role_id) not in recent_messages_set:
                # Format the birthday message
                message = f"# 🎉 Happy Birthday, {member_name}! 🎂"
                gif_url = get_random_link_for_each_role([role_id], "18 year")[0][1]

                try:
                    # 5. Send the message via Discord
                    guild = bot.get_guild(guild_id)
                    if guild is None:
                        continue  # Skip if the bot is not part of the guild

                    channel = guild.get_channel(channel_id)
                    if channel is None:
                        continue  # Skip if the channel is not found

                    await channel.send(message)
                    await channel.send(gif_url)

                    # Log the sent message immediately
                    log_message(guild_id, channel_id, role_id)

                    # Add the sent message to the recent messages set to prevent duplicates in the same run
                    recent_messages_set.add((guild_id, channel_id, role_id))

                except Exception as e:
                    print(f"Failed to send message to guild {guild_id}, channel {channel_id}: {e}")

    print("Completed birthday feeds.")
