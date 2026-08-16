"""Compact, public reporting controls for delivered content links."""

import asyncio
from typing import Literal

import discord

from src.db.utils import add_content_report
from src.rate_limit import RecentPairRateLimiter

ReportReason = Literal["broken_link", "wrong_idol"]
_report_rate_limiter = RecentPairRateLimiter(cooldown_seconds=5 * 60, capacity=20)


class ContentReportReasonView(discord.ui.View):
    """Ephemeral second step so an accidental tap does not record a report."""

    def __init__(self, role_id: str, url: str):
        super().__init__(timeout=60)
        self.role_id = role_id
        self.url = url

    async def _record(self, interaction: discord.Interaction, reason: ReportReason) -> None:
        if not _report_rate_limiter.allow(interaction.user.id, self.role_id):
            await interaction.response.edit_message(
                content="You can report this idol again in a few minutes.",
                view=None,
            )
            return
        await asyncio.to_thread(add_content_report, self.role_id, self.url, reason)
        label = "broken-link" if reason == "broken_link" else "wrong-idol/group"
        await interaction.response.edit_message(content=f"Thanks — your {label} report was recorded.", view=None)

    @discord.ui.button(label="Broken link", style=discord.ButtonStyle.secondary, emoji="🔗")
    async def broken_link_button(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self._record(interaction, "broken_link")

    @discord.ui.button(label="Wrong idol / group", style=discord.ButtonStyle.secondary, emoji="🏷️")
    async def wrong_idol_button(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self._record(interaction, "wrong_idol")


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
        await interaction.response.send_message(
            "What should we fix?",
            view=ContentReportReasonView(self.role_id, self.url),
            ephemeral=True,
        )


class ContentReportView(discord.ui.View):
    """A low-profile control attached directly to each delivered content URL."""

    def __init__(self, role_id: str, url: str):
        super().__init__(timeout=None)
        self.add_item(ContentReportButton(role_id, url))
