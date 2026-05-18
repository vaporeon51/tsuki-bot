import io
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlparse

import asyncpraw
import asyncpraw.models
import discord
import requests
from discord.ext import commands

from src.config.constants import REDDIT_MAX_ATTACHMENTS
from src.db.reddit_feeds import get_feed_configs

REDDIT_CLIENT_ID = os.environ["REDDIT_CLIENT_ID"]
REDDIT_SECRET = os.environ["REDDIT_SECRET"]


@dataclass
class RedditPost:
    title: str
    created_utc: float
    is_gallery: bool
    media_urls: list[str]


def get_reddit_video_url(post: asyncpraw.models.Submission) -> str:
    """Return the playable fallback URL for a Reddit-hosted video."""
    post_data = post.__dict__
    media_sources = [
        post_data.get("secure_media"),
        post_data.get("media"),
    ]

    for crosspost in post_data.get("crosspost_parent_list") or []:
        media_sources.extend(
            [
                crosspost.get("secure_media"),
                crosspost.get("media"),
            ]
        )

    for media in media_sources:
        if not media:
            continue
        reddit_video = media.get("reddit_video")
        if reddit_video and reddit_video.get("fallback_url"):
            return reddit_video["fallback_url"]

    raise ValueError(f"Could not find reddit video URL for {post.url}.")


def get_gallery_urls(post: asyncpraw.models.Submission) -> list[str]:
    """Return source media URLs for a Reddit gallery."""
    post_data = post.__dict__
    gallery_sources = [post_data]
    gallery_sources.extend(post_data.get("crosspost_parent_list") or [])

    for source_data in gallery_sources:
        media_metadata = source_data.get("media_metadata")
        if not media_metadata:
            continue

        gallery_items = (source_data.get("gallery_data") or {}).get("items") or []
        if gallery_items:
            images = [
                media_metadata[item["media_id"]]
                for item in gallery_items
                if item.get("media_id") in media_metadata
            ]
        else:
            images = media_metadata.values()

        media_urls = []
        for image in images:
            source = image["s"]
            if "u" in source:
                media_urls.append(unescape(source["u"]))
            elif "gif" in source:
                media_urls.append(unescape(source["gif"]))
            else:
                raise ValueError(f"Can't find good keys in {post.url}.")
        return media_urls

    raise ValueError(f"Could not find gallery media metadata for {post.url}.")


async def get_latest_posts(subreddit: str) -> list[asyncpraw.models.Submission]:
    """Get latest posts from kpopfap subreddit."""
    reddit = asyncpraw.Reddit(
        client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_SECRET, user_agent="tsuki-bot"
    )
    subreddit = await reddit.subreddit(subreddit)
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
        media_urls = get_gallery_urls(post)
    elif "v.redd.it" in post.url:
        # For uploaded videos (non-imgur)
        is_gallery = True
        media_urls = [get_reddit_video_url(post)]
    else:
        is_gallery = False
        media_urls = [post.url]
    return RedditPost(
        title=post.title,
        created_utc=post.created_utc,
        is_gallery=is_gallery,
        media_urls=media_urls,
    )


async def get_and_parse_posts(subreddit: str) -> list[RedditPost]:
    """Fetch and parse latest posts for a subreddit."""
    try:
        posts = await get_latest_posts(subreddit)
    except Exception as e:
        print(f"Could not get posts from subreddit: {subreddit}. Error: {str(e)}")
        return []

    parsed_posts: list[RedditPost] = []
    for post in posts:
        try:
            parsed_posts.append(parse_post(post))
        except Exception as e:
            print(f"Could not parse post {post.title} from subreddit {subreddit}. Error: {str(e)}")
            continue

    return parsed_posts


async def update_reddit_feeds(bot: commands.Bot, lookback_secs: int) -> None:
    """Main routine for scanning new kpopfap reddit posts and sending updates."""

    print("Updating reddit feeds...")
    curr_time = datetime.now(timezone.utc).timestamp()
    feed_configs = get_feed_configs()
    num_new_posts = {}
    try:
        all_subreddits = set(subreddit for _, _, subreddit in feed_configs)
        posts_by_subreddit = {}

        for subreddit in all_subreddits:
            parsed_posts = await get_and_parse_posts(subreddit)
            recent_posts = [
                post for post in parsed_posts if curr_time - post.created_utc < lookback_secs
            ]
            posts_by_subreddit[subreddit] = sorted(recent_posts, key=lambda x: x.created_utc)
            num_new_posts[subreddit] = len(recent_posts)

    except Exception as e:
        print(f"Error with fetching latest posts: {str(e)}")
        return

    # Send those posts
    for guild_id, channel_id, subreddit in feed_configs:
        try:
            if bot.get_guild(guild_id):
                if channel := bot.get_channel(channel_id):
                    for post in posts_by_subreddit.get(subreddit, []):
                        text = f"[r/{subreddit}] **{post.title}**"
                        if post.is_gallery:
                            images = get_image_files(post.media_urls)
                            await channel.send(text, files=images)
                        else:
                            await channel.send(text)
                            await channel.send(post.media_urls[0])
        except Exception as e:
            print(f"Error with sending post ({guild_id}, {channel_id}, {subreddit})")
    print(f"Update complete with {num_new_posts} posts.")
