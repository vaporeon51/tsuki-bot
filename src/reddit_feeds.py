import io
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import asyncpraw
import asyncpraw.models
import discord
import requests
from discord.ext import commands

from src.config.constants import REDDIT_MAX_ATTACHMENTS, TSUKI_CUTE
from src.db.reddit_feeds import get_feed_configs

REDDIT_CLIENT_ID = os.environ["REDDIT_CLIENT_ID"]
REDDIT_SECRET = os.environ["REDDIT_SECRET"]


@dataclass
class RedditPost:
    title: str
    created_utc: float
    is_gallery: bool
    media_urls: list[str]


async def get_latest_posts() -> list[asyncpraw.models.Submission]:
    """Get latest posts from kpopfap subreddit."""
    reddit = asyncpraw.Reddit(client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_SECRET, user_agent="tsuki-bot")
    subreddit = await reddit.subreddit("kpopfap")
    posts = []
    async for post in subreddit.new(limit=10):
        posts.append(post)
    await reddit.close()
    return posts


def get_image_files(urls: list[str]) -> list[discord.File]:
    """Download reddit images and turn them into discord file attachments."""
    results = []
    for url in urls[:REDDIT_MAX_ATTACHMENTS]:
        response = requests.get(url)
        if response.status_code == 200:
            image_data = io.BytesIO(response.content)
            parsed_url = urlparse(url)
            filename = parsed_url.path.split("/")[-1]
            results.append(discord.File(fp=image_data, filename=filename))
        else:
            print(f"Failed to get url: {url}. Response: {response.json()}")
    return results


def parse_post(post: asyncpraw.models.Submission) -> RedditPost:
    """Parse a single reddit post."""
    if "gallery" in post.url:
        is_gallery = True
        # We have to extract the proper CDN urls from each image
        media_urls = [image["s"]["u"] for image in post.__dict__["media_metadata"].values()]
    else:
        is_gallery = False
        media_urls = [post.url]
    return RedditPost(
        title=post.title,
        created_utc=post.created_utc,
        is_gallery=is_gallery,
        media_urls=media_urls,
    )


async def update_reddit_feeds(bot: commands.Bot, lookback_secs: int) -> None:
    """Main routine for scanning new kpopfap reddit posts and sending updates."""

    print("Updating reddit feeds...")
    curr_time = datetime.now(timezone.utc).timestamp()
    feed_configs = get_feed_configs()

    try:
        posts = await get_latest_posts()
    except Exception as e:
        print(f"Error with fetching latest posts: {str(e)}")
        return

    # Get the posts that are in the lookback window
    parsed_posts: list[RedditPost] = []
    for post in posts:
        parsed_post = parse_post(post)
        if curr_time - parsed_post.created_utc < lookback_secs:
            parsed_posts.append(parsed_post)
    parsed_posts = sorted(parsed_posts, key=lambda x: x.created_utc)

    # Send those posts
    for guild_id, channel_id in feed_configs:
        if bot.get_guild(guild_id):
            if channel := bot.get_channel(channel_id):
                for post in parsed_posts:
                    text = f"[r/kpopfap] **{post.title}** {TSUKI_CUTE}"
                    if post.is_gallery:
                        images = get_image_files(post.media_urls)
                        await channel.send(text, files=images)
                    else:
                        await channel.send(text)
                        await channel.send(post.media_urls[0])
    print(f"Update complete with {len(parsed_posts)} posts.")
