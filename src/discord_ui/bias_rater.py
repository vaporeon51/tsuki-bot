import asyncio

import discord

from src.db.bias_rater import get_matchup, record_vote
from src.db.stats import add_stat_count

# Discord renders multiple embeds that share the same `url` as a single gallery
# card with their images laid out side-by-side. Any valid, non-empty URL works —
# it just has to match across all the embeds we want grouped.
_EMBED_GROUP_URL = "https://github.com/vaporeon51/tsuki-bot"


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


def build_round_embeds(
    left_idol, right_idol, round_num: int, total_rounds: int
) -> list[discord.Embed]:
    # idol = (role_id, member_name, group_name, global_elo, image_url)
    header = discord.Embed(
        title=f"Head to Head (Round {round_num}/{total_rounds})",
        description=(
            f"⬅️ **{left_idol[1]}** ({left_idol[2]}) — ELO {left_idol[3]}\n"
            f"➡️ **{right_idol[1]}** ({right_idol[2]}) — ELO {right_idol[3]}\n\n"
            "Vote for your bias!"
        ),
        color=discord.Color.blue(),
        url=_EMBED_GROUP_URL,
    )
    if left_idol[4]:
        header.set_image(url=left_idol[4])

    right = discord.Embed(url=_EMBED_GROUP_URL)
    if right_idol[4]:
        right.set_image(url=right_idol[4])

    return [header, right]


def build_leaderboard_embeds(
    title: str, tops: list[tuple[str, str, int, str]]
) -> list[discord.Embed]:
    """Header embed with the ranked list + #1 image, plus gallery embeds for #2 and #3."""
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    lines = []
    for rank, (name, group, elo, _) in enumerate(tops, 1):
        prefix = medals.get(rank, f"**#{rank}**")
        lines.append(f"{prefix}  **{name}** · {group} — **{elo}**")

    header = discord.Embed(
        title=f"🏆 {title}",
        description="\n".join(lines) if lines else "No entries yet.",
        color=discord.Color.gold(),
        url=_EMBED_GROUP_URL,
    )
    if tops and tops[0][3]:
        header.set_image(url=tops[0][3])

    embeds = [header]
    for rank in (2, 3):
        if len(tops) >= rank and tops[rank - 1][3]:
            podium = discord.Embed(url=_EMBED_GROUP_URL)
            podium.set_image(url=tops[rank - 1][3])
            embeds.append(podium)

    return embeds


def build_result_embed(
    winner, loser, gw: int, gl: int, sw: int, sl: int, pw: int, pl: int
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{winner[1]} won!",
        description=f"**{winner[1]}** ({winner[2]}) over {loser[1]} ({loser[2]})",
        color=discord.Color.green(),
    )
    embed.add_field(name="Global ELO", value=f"Winner: +{gw} | Loser: {gl}", inline=False)
    embed.add_field(name="Server ELO", value=f"Winner: +{sw} | Loser: {sl}", inline=False)
    embed.add_field(name="Personal ELO", value=f"Winner: +{pw} | Loser: {pl}", inline=False)
    if winner[4]:
        embed.set_image(url=winner[4])
    return embed


class VoteView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        guild_id: int,
        total_rounds: int,
        matchup,
        current_round: int = 1,
        matchups_log: list | None = None,
    ):
        super().__init__(timeout=60.0)
        self.user_id = user_id
        self.guild_id = guild_id
        self.total_rounds = total_rounds
        self.current_round = current_round
        self.matchups_log = matchups_log or []

        self.left_idol, self.right_idol = matchup[0], matchup[1]
        self.embeds = build_round_embeds(
            self.left_idol, self.right_idol, self.current_round, self.total_rounds
        )

    @classmethod
    async def create(
        cls,
        user_id: int,
        guild_id: int,
        total_rounds: int,
        current_round: int = 1,
        matchups_log: list | None = None,
    ) -> "VoteView":
        # Matchup fetch hits the DB, keep it off the event loop
        matchup = await asyncio.to_thread(get_matchup, user_id)
        if not matchup:
            raise ValueError("Not enough idols to match up!")
        return cls(user_id, guild_id, total_rounds, matchup, current_round, matchups_log)

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
        # Ack immediately so we don't trip Discord's 3s interaction deadline
        # while record_vote's sync DB work is running in a worker thread.
        await interaction.response.defer()

        # 0 = left, 1 = right
        winner = self.left_idol if winner_idx == 0 else self.right_idol
        loser = self.right_idol if winner_idx == 0 else self.left_idol

        # Disable buttons
        for item in self.children:
            item.disabled = True

        # Process ELO (sync DB work pushed to a worker thread)
        gw, gl, sw, sl, pw, pl = await asyncio.to_thread(
            record_vote, self.user_id, self.guild_id, winner[0], loser[0]
        )
        await asyncio.to_thread(add_stat_count, "bias_vote_cast")
        self.matchups_log.append((winner[1], loser[1], winner[2], loser[2], gw))

        # Collapse to a single result embed so the winner's image gets the full frame
        self.embeds = [build_result_embed(winner, loser, gw, gl, sw, sl, pw, pl)]
        await interaction.edit_original_response(embeds=self.embeds, view=self)

        # Trigger next round or summary
        if self.current_round < self.total_rounds:
            await asyncio.sleep(1.5)
            next_view = await VoteView.create(
                self.user_id,
                self.guild_id,
                self.total_rounds,
                self.current_round + 1,
                self.matchups_log,
            )
            await interaction.edit_original_response(embeds=next_view.embeds, view=next_view)
        else:
            await asyncio.sleep(1.5)
            summary_embed = VoteSummaryEmbed(self.matchups_log)
            # Post as a standalone channel message (not via interaction.followup)
            # so it doesn't render as a reply to the ephemeral voting card.
            await interaction.channel.send(embed=summary_embed)
            await interaction.edit_original_response(
                content="Session complete — summary posted.",
                embeds=[],
                view=None,
            )

    @discord.ui.button(label="⬅️ Left", style=discord.ButtonStyle.primary)
    async def left_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 0)

    @discord.ui.button(label="➡️ Right", style=discord.ButtonStyle.primary)
    async def right_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 1)
