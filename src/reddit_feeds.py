import asyncio
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import asyncpraw
import asyncpraw.models
import asyncprawcore
import discord
import requests
from discord.ext import commands

from src.config.constants import REDDIT_MAX_ATTACHMENT_BYTES, REDDIT_MAX_ATTACHMENTS
from src.db.reddit_feeds import get_feed_configs, unset_subreddit_feeds

REDDIT_CLIENT_ID = os.environ["REDDIT_CLIENT_ID"]
REDDIT_SECRET = os.environ["REDDIT_SECRET"]
UNRECOVERABLE_SUBREDDIT_STATUSES = {403, 404, 410, 451}
UNRECOVERABLE_SUBREDDIT_REDIRECT_PATHS = {"/subreddits/search"}


@dataclass
class RedditPost:
    title: str
    created_utc: float
    is_gallery: bool
    media_urls: list[str]


@dataclass
class RedditFetchResult:
    posts: list[RedditPost]
    should_unsubscribe: bool = False


def is_unrecoverable_subreddit_error(error: Exception) -> bool:
    """Return whether the subreddit cannot be fetched by this bot in future cycles."""
    if isinstance(error, asyncprawcore.exceptions.Redirect):
        return error.path in UNRECOVERABLE_SUBREDDIT_REDIRECT_PATHS

    if not isinstance(error, asyncprawcore.exceptions.ResponseException):
        return False

    status = getattr(error.response, "status", None)
    return status in UNRECOVERABLE_SUBREDDIT_STATUSES


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
                media_metadata[item["media_id"]] for item in gallery_items if item.get("media_id") in media_metadata
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
    reddit = asyncpraw.Reddit(client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_SECRET, user_agent="tsuki-bot")
    try:
        subreddit_obj = await reddit.subreddit(subreddit)
        posts = []
        async for post in subreddit_obj.new(limit=10):
            posts.append(post)
        return posts
    finally:
        await reddit.close()


def get_media_files(urls: list[str], output_dir: Path) -> list[discord.File]:
    """Stream Reddit media to temporary files and open Discord attachments."""

    results: list[discord.File] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, url in enumerate(urls[:REDDIT_MAX_ATTACHMENTS]):
        output_path: Path | None = None
        try:
            filename = Path(urlparse(url).path).name or f"reddit-media-{index}"
            output_path = output_dir / f"{index}-{filename}"
            with requests.get(url, stream=True, timeout=(10, 60)) as response:
                if response.status_code != 200:
                    print(f"Failed to get url: {url}. Status: {response.status_code}")
                    continue

                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit() and int(content_length) > REDDIT_MAX_ATTACHMENT_BYTES:
                    print(f"Skipped oversized Reddit attachment: {url}")
                    continue

                downloaded_bytes = 0
                with output_path.open("wb") as output_file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > REDDIT_MAX_ATTACHMENT_BYTES:
                            raise ValueError("attachment exceeds the download safety limit")
                        output_file.write(chunk)

            results.append(discord.File(fp=output_path, filename=filename))
        except Exception as e:
            print(f"Error fetching URL {url}: {e}")
            if output_path is not None:
                output_path.unlink(missing_ok=True)
    return results


def close_media_files(files: list[discord.File]) -> None:
    for media_file in files:
        media_file.close()


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


async def get_and_parse_posts(subreddit: str) -> RedditFetchResult:
    """Fetch and parse latest posts for a subreddit."""
    try:
        posts = await get_latest_posts(subreddit)
    except Exception as e:
        print(f"Could not get posts from subreddit: {subreddit}. Error: {str(e)}")
        return RedditFetchResult(posts=[], should_unsubscribe=is_unrecoverable_subreddit_error(e))

    parsed_posts: list[RedditPost] = []
    for post in posts:
        try:
            parsed_posts.append(parse_post(post))
        except Exception as e:
            print(f"Could not parse post {post.title} from subreddit {subreddit}. Error: {str(e)}")
            continue

    return RedditFetchResult(posts=parsed_posts)


async def update_reddit_feeds(bot: commands.Bot, lookback_secs: int) -> None:
    """Main routine for scanning new kpopfap reddit posts and sending updates."""

    print("Updating reddit feeds...")
    curr_time = datetime.now(timezone.utc).timestamp()
    feed_configs = await asyncio.to_thread(get_feed_configs)
    num_new_posts = {}
    try:
        all_subreddits = set(subreddit for _, _, subreddit in feed_configs)
        posts_by_subreddit = {}

        for subreddit in all_subreddits:
            fetch_result = await get_and_parse_posts(subreddit)
            if fetch_result.should_unsubscribe:
                deleted_count = await asyncio.to_thread(unset_subreddit_feeds, subreddit)
                print(f"Removed {deleted_count} reddit feed subscriptions for unrecoverable subreddit: {subreddit}")
                continue

            recent_posts = [post for post in fetch_result.posts if curr_time - post.created_utc < lookback_secs]
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
                            with tempfile.TemporaryDirectory(prefix="reddit-feed-") as temporary_dir:
                                files = await asyncio.to_thread(get_media_files, post.media_urls, Path(temporary_dir))
                                try:
                                    if files:
                                        await channel.send(text, files=files)
                                    else:
                                        await channel.send(text)
                                finally:
                                    close_media_files(files)
                        else:
                            await channel.send(text)
                            await channel.send(post.media_urls[0])
        except Exception:
            print(f"Error with sending post ({guild_id}, {channel_id}, {subreddit})")
    print(f"Update complete with {num_new_posts} posts.")
