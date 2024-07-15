from dataclasses import dataclass
from datetime import datetime, timezone

import requests
from discord.ext import commands

from src.db.reddit_feeds import get_feed_configs


@dataclass
class RedditPost:
    title: str
    created_utc: float
    is_gallery: bool
    media_urls: list[str]


def get_latest_posts() -> list[dict]:
    """Get a latest posts from r/kpopfap."""
    resp = requests.get("http://www.reddit.com/r/kpopfap/new.json?sort=new")
    return resp.json()


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
        title=data["title"],
        created_utc=data["created_utc"],
        is_gallery=is_gallery,
        media_urls=media_urls,
    )


async def update_feeds(bot: commands.Bot, lookback_secs: int) -> None:
    """Main routine for scanning new kpopfap reddit posts and sending updates."""

    feed_configs = get_feed_configs()
    response = get_latest_posts()

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
    posts = sorted(posts, key=lambda post: post.created_utc, reverse=True)

    # Send those posts
    for guild_id, channel_id in feed_configs:
        if bot.get_guild(guild_id):
            if channel := bot.get_channel(channel_id):
                for post in posts:
                    await channel.send(f"**{post.title}** posted to r/kpopfap")
                    for url in post.media_urls:
                        await channel.send(url)
