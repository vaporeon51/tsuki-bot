import asyncio

import discord

from src.db.bias_rater import get_matchup, record_vote


class VoteSummaryEmbed(discord.Embed):
    def __init__(self, matchups: list[tuple[str, str, str, str, int]]):
        """
        matchups contains: (winner_name, loser_name, winner_group, loser_group, winner_global_delta)
        """
        super().__init__(
            title="Bias Rater Session Summary",
            color=discord.Color.purple(),
        )
        description_lines = []
        for i, (w_name, l_name, w_group, l_group, w_delta) in enumerate(matchups, 1):
            w_disp = f"**{w_name}** ({w_group})"
            l_disp = f"{l_name} ({l_group})"
            description_lines.append(f"**{i}.** {w_disp} vs {l_disp} ➔ **{w_name}** (+{w_delta})")

        self.description = "\n".join(description_lines) if description_lines else "No votes cast."


class VoteRoundEmbed(discord.Embed):
    def __init__(self, left_idol, right_idol, round_num: int, total_rounds: int):
        # idol = (role_id, member_name, group_name, global_elo, image_url)
        super().__init__(
            title=f"Head to Head (Round {round_num}/{total_rounds})",
            description="Vote for your bias! Who do you prefer?",
            color=discord.Color.blue(),
        )
        self.add_field(
            name="⬅️ Left",
            value=f"**{left_idol[1]}**\n{left_idol[2]}\n*Global ELO: {left_idol[3]}*",
            inline=True,
        )
        self.add_field(
            name="➡️ Right",
            value=f"**{right_idol[1]}**\n{right_idol[2]}\n*Global ELO: {right_idol[3]}*",
            inline=True,
        )

        # We can't display two side-by-side images easily in a single embed,
        # so we'll just set one image and one thumbnail if both exist,
        # or combine them if desired, but discord embeds natively only support 1 main image and 1 thumbnail.
        if left_idol[4] or right_idol[4]:
            if left_idol[4] and right_idol[4]:
                self.set_image(url=left_idol[4])
                self.set_thumbnail(url=right_idol[4])
            else:
                self.set_image(url=left_idol[4] or right_idol[4])


class VoteView(discord.ui.View):
    def __init__(self, user_id: int, total_rounds: int, current_round: int = 1, matchups_log=None):
        super().__init__(timeout=60.0)
        self.user_id = user_id
        self.total_rounds = total_rounds
        self.current_round = current_round
        self.matchups_log = matchups_log or []

        # Get matchup
        matchup = get_matchup(self.user_id)
        if not matchup:
            raise ValueError("Not enough idols to match up!")

        self.left_idol, self.right_idol = matchup[0], matchup[1]
        self.embed = VoteRoundEmbed(
            self.left_idol, self.right_idol, self.current_round, self.total_rounds
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

        # If we time out, we can try to show a summary of what's been done,
        # but since we can't edit the message without passing the message object to on_timeout
        # (which requires holding a reference), we'll just let it die for now.
        pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your voting session!", ephemeral=True
            )
            return False
        return True

    async def process_vote(self, interaction: discord.Interaction, winner_idx: int):
        # 0 = left, 1 = right
        winner = self.left_idol if winner_idx == 0 else self.right_idol
        loser = self.right_idol if winner_idx == 0 else self.left_idol

        # Disable buttons
        for item in self.children:
            item.disabled = True

        # Process ELO
        gw, gl, pw, pl = record_vote(self.user_id, winner[0], loser[0])
        self.matchups_log.append((winner[1], loser[1], winner[2], loser[2], gw))

        # Update Embed to show result
        self.embed.clear_fields()
        self.embed.description = f"**{winner[1]}** won! ELO updated."
        self.embed.add_field(name="Global ELO", value=f"Winner: +{gw} | Loser: {gl}", inline=False)
        self.embed.add_field(
            name="Personal ELO", value=f"Winner: +{pw} | Loser: {pl}", inline=False
        )

        await interaction.response.edit_message(embed=self.embed, view=self)

        # Trigger next round or summary
        if self.current_round < self.total_rounds:
            await asyncio.sleep(1.5)
            next_view = VoteView(
                self.user_id, self.total_rounds, self.current_round + 1, self.matchups_log
            )
            # Use original response to edit it with the new view
            await interaction.edit_original_response(embed=next_view.embed, view=next_view)
        else:
            await asyncio.sleep(1.5)
            summary_embed = VoteSummaryEmbed(self.matchups_log)
            await interaction.edit_original_response(embed=summary_embed, view=None)

    @discord.ui.button(label="⬅️ Left", style=discord.ButtonStyle.primary)
    async def left_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 0)

    @discord.ui.button(label="➡️ Right", style=discord.ButtonStyle.primary)
    async def right_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 1)
