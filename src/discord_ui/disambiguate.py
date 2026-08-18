"""Minimal admin UI for resolving the roles associated with one content URL."""

import asyncio

import discord

from src.db.utils import DisambiguationCandidate, apply_disambiguation


def _option_label(label: str) -> str:
    """Discord select labels are limited to 100 characters."""

    return label if len(label) <= 100 else f"{label[:97]}..."


class RoleSelect(discord.ui.Select):
    def __init__(self, candidate: DisambiguationCandidate):
        super().__init__(
            placeholder="Select every relevant role",
            min_values=0,
            max_values=len(candidate.roles),
            options=[
                discord.SelectOption(label=_option_label(role.label), value=role.role_id) for role in candidate.roles
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if isinstance(self.view, DisambiguationView):
            self.view.selected_role_ids = tuple(self.values)
        await interaction.response.defer()


class DisambiguationView(discord.ui.View):
    """Let the command invoker retain every role that is relevant to one URL."""

    def __init__(self, user_id: int, candidate: DisambiguationCandidate):
        super().__init__(timeout=15 * 60)
        self.user_id = user_id
        self.candidate = candidate
        self.selected_role_ids: tuple[str, ...] = ()
        self.message: discord.Message | None = None

        self.role_select = RoleSelect(candidate)
        self.add_item(self.role_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("This is someone else's disambiguation session.", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Save", style=discord.ButtonStyle.success)
    async def save_button(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer()
        updated = await asyncio.to_thread(apply_disambiguation, self.candidate.url, self.selected_role_ids)
        self.stop()
        message = interaction.message or self.message
        if message is not None:
            await message.edit(view=None)

        selected_labels = [role.label for role in self.candidate.roles if role.role_id in self.selected_role_ids]
        kept = ", ".join(selected_labels) if selected_labels else "no roles"
        await interaction.followup.send(f"Saved {updated} rows. Kept: {kept}.")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer()
        self.stop()
        message = interaction.message or self.message
        if message is not None:
            await message.edit(view=None)
        await interaction.followup.send("Skipped; this URL remains unresolved.")
