"""Compact, public reporting controls for delivered content links."""

import asyncio
from typing import Literal

import discord

from src.db.utils import ContentVoteScore, add_content_report, add_content_vote, get_content_vote_score
from src.rate_limit import RecentPairRateLimiter

_report_rate_limiter = RecentPairRateLimiter(cooldown_seconds=5 * 60, capacity=20)
_vote_rate_limiter = RecentPairRateLimiter(cooldown_seconds=5 * 60, capacity=20)


class ContentReportButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"content_report:(?P<role_id>[^:]{1,80})",
):
    """Persistent report button whose target URL is the message's only content."""

    def __init__(self, role_id: str, url: str):
        self.role_id = role_id
        self.url = url
        super().__init__(
            discord.ui.Button(
                label="Report issue",
                style=discord.ButtonStyle.secondary,
                emoji=discord.PartialEmoji(name="important", id=1538368125127360652),
                custom_id=f"content_report:{role_id}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        _item: discord.ui.Button,
        match,
    ) -> "ContentReportButton":
        url = interaction.message.content.strip() if interaction.message is not None else ""
        return cls(match["role_id"], url)

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.url:
            await interaction.response.send_message("I couldn't identify this content item.", ephemeral=True)
            return
        if not _report_rate_limiter.allow(interaction.user.id, self.url):
            await interaction.response.send_message("You've already reported this link recently.", ephemeral=True)
            return
        await asyncio.to_thread(add_content_report, self.role_id, self.url)
        await interaction.response.send_message("Thanks! Your report was recorded.", ephemeral=True)


class ContentVoteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"content_vote:(?P<direction>up|down):(?P<role_id>[^:]{1,80})",
):
    """Persistent up/down control whose target URL is the message's only content."""

    def __init__(self, role_id: str, url: str, direction: Literal["up", "down"]):
        self.role_id = role_id
        self.url = url
        self.direction = direction
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=discord.PartialEmoji(
                    name="small_green_triangle_up31" if direction == "up" else "small_red_triangle_down31",
                    id=1538379192104914994 if direction == "up" else 1538379272383758436,
                ),
                custom_id=f"content_vote:{direction}:{role_id}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        _item: discord.ui.Button,
        match,
    ) -> "ContentVoteButton":
        url = interaction.message.content.strip() if interaction.message is not None else ""
        return cls(match["role_id"], url, match["direction"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.url:
            await interaction.response.send_message("I couldn't identify this content item.", ephemeral=True)
            return
        if not _vote_rate_limiter.allow(interaction.user.id, self.url):
            await interaction.response.defer()
            return
        score = await asyncio.to_thread(add_content_vote, self.role_id, self.url, self.direction)
        await interaction.response.edit_message(view=ContentFeedbackView(self.role_id, self.url, score))


class ContentFeedbackView(discord.ui.View):
    """A compact voting and reporting control attached to each delivered URL."""

    def __init__(self, role_id: str, url: str, score: ContentVoteScore):
        super().__init__(timeout=None)
        self.add_item(ContentVoteButton(role_id, url, "up"))
        self.add_item(
            discord.ui.Button(
                label=f"{score.value:+d}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
            )
        )
        self.add_item(ContentVoteButton(role_id, url, "down"))
        self.add_item(ContentReportButton(role_id, url))

    @classmethod
    async def create(cls, role_id: str, url: str) -> "ContentFeedbackView":
        score = await asyncio.to_thread(get_content_vote_score, role_id, url)
        return cls(role_id, url, score)
