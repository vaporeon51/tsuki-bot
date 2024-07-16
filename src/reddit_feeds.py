import io
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import discord
import requests
from discord.ext import commands

from src.config.constants import TSUKI_CUTE
from src.db.reddit_feeds import get_feed_configs


@dataclass
class RedditPost:
    title: str
    created_utc: float
    is_gallery: bool
    media_urls: list[str]


def get_latest_posts() -> list[dict]:
    """Get a latest posts from r/kpopfap."""

    # Use header to avoid very aggressive 429 rate limiting
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    resp = requests.get("https://www.reddit.com/r/kpopfap/new.json?sort=new", headers=headers, timeout=5)
    return resp.json()


def get_image_files(urls: list[str]) -> list[discord.File]:
    """Download reddit images and turn them into discord file attachments."""
    results = []
    for url in urls:
        response = requests.get(url)
        if response.status_code == 200:
            image_data = io.BytesIO(response.content)
            parsed_url = urlparse(url)
            filename = parsed_url.path.split("/")[-1]
            results.append(discord.File(fp=image_data, filename=filename))
        else:
            print(f"Failed to get url: {url}. Response: {response.json()}")
    return results


def parse_post(json_obj: dict) -> RedditPost:
    """Parse a single reddit post."""
    data = json_obj["data"]
    if "gallery" in data["url"]:
        is_gallery = True
        # We have to extract the proper CDN urls from each image
        media_urls = [image["s"]["u"].replace("&amp;", "&") for image in data["media_metadata"].values()]
    else:
        is_gallery = False
        media_urls = [data["url"]]
    return RedditPost(
        title=data["title"].replace("&amp;", "&"),
        created_utc=data["created_utc"],
        is_gallery=is_gallery,
        media_urls=media_urls,
    )


async def update_reddit_feeds(bot: commands.Bot, lookback_secs: int) -> None:
    """Main routine for scanning new kpopfap reddit posts and sending updates."""

    print("Updating reddit feeds...")
    feed_configs = get_feed_configs()
    print("Got configs", feed_configs)
    response = get_latest_posts()
    print("Got responses")

    # Sometimes we hit rate limit
    if "data" not in response:
        print(f"No data from response: {response}")
        return

    curr_time = datetime.now(timezone.utc).timestamp()

    # Get the posts that are in the lookback window
    posts: list[RedditPost] = []
    for entry in response["data"]["children"]:
        post = parse_post(entry)
        if curr_time - post.created_utc < lookback_secs:
            posts.append(post)
    posts = sorted(posts, key=lambda post: post.created_utc)
    print("Filtered posts", posts)

    # Send those posts
    for guild_id, channel_id in feed_configs:
        if bot.get_guild(guild_id):
            if channel := bot.get_channel(channel_id):
                for post in posts:
                    text = f"[r/kpopfap] **{post.title}** {TSUKI_CUTE}"
                    if post.is_gallery:
                        images = get_image_files(post.media_urls)
                        await channel.send(text, files=images)
                    else:
                        await channel.send(text)
                        await channel.send(post.media_urls[0])
    print(f"Update complete with {len(posts)} posts.")
