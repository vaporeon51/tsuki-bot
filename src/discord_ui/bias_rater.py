import asyncio
from dataclasses import dataclass, field

import discord

from src.db.bias_rater import (
    get_daily_idols,
    get_matchup,
    record_daily_completion,
    record_vote,
)
from src.db.stats import add_stat_count

# Discord renders multiple embeds that share the same `url` as a single gallery
# card with their images laid out side-by-side. Any valid, non-empty URL works —
# it just has to match across all the embeds we want grouped.
_EMBED_GROUP_URL = "https://github.com/vaporeon51/tsuki-bot"


@dataclass
class MatchupLog:
    left_name: str
    left_group: str
    right_name: str
    right_group: str
    winner_idx: int


@dataclass
class BracketState:
    """Tracks an 8-idol single-elimination bracket: 4 QFs → 2 SFs → 1 final (7 matches).

    current_round_idols: contestants still awaiting a match this round. Pair 0/1
    is the currently-displayed matchup. After a winner is recorded, [0:2] is
    removed and the winner appended to winners_so_far. When current_round_idols
    empties, winners_so_far becomes the next round's lineup.
    """

    current_round_idols: list
    winners_so_far: list = field(default_factory=list)
    total_matches_played: int = 0

    def current_pair(self):
        if len(self.current_round_idols) < 2:
            return None
        return (self.current_round_idols[0], self.current_round_idols[1])

    def record_winner(self, winner) -> None:
        self.current_round_idols = self.current_round_idols[2:]
        self.winners_so_far.append(winner)
        self.total_matches_played += 1
        if not self.current_round_idols and len(self.winners_so_far) > 1:
            self.current_round_idols = self.winners_so_far
            self.winners_so_far = []

    def is_complete(self) -> bool:
        return self.total_matches_played >= 7

    def round_label(self) -> str:
        # Based on the match about to be voted on (zero-indexed by matches_played)
        idx = self.total_matches_played
        if idx < 4:
            return "Quarterfinal"
        if idx < 6:
            return "Semifinal"
        return "Final"

    def champion(self):
        return self.winners_so_far[0] if self.is_complete() and self.winners_so_far else None


class VoteSummaryEmbed(discord.Embed):
    def __init__(
        self,
        matchups: list[MatchupLog],
        voter_name: str | None = None,
        voter_icon_url: str | None = None,
    ):
        """
        matchups contains a list of MatchupLog instances.
        """
        super().__init__(
            title="Bias Rater Session Summary",
            color=discord.Color.purple(),
        )
        if voter_name:
            self.set_author(name=voter_name, icon_url=voter_icon_url)
        description_lines = []
        for i, log in enumerate(matchups, 1):
            if log.winner_idx == 0:
                l_disp = f"**{log.left_name}** ({log.left_group})"
                r_disp = f"{log.right_name} ({log.right_group})"
            else:
                l_disp = f"{log.left_name} ({log.left_group})"
                r_disp = f"**{log.right_name}** ({log.right_group})"
            description_lines.append(f"**{i}.** {l_disp} vs {r_disp}")

        self.description = "\n".join(description_lines) if description_lines else "No votes cast."
        self.set_footer(text="Run `/bias leaderboard` to see your updated bias list!")


def build_round_embeds(left_idol, right_idol, round_num: int) -> list[discord.Embed]:
    # idol = (role_id, member_name, group_name, global_elo, image_url)
    header = discord.Embed(
        title=f"Head to Head (Round {round_num})",
        description=(
            f"⬅️ **{left_idol[1]}** ({left_idol[2]})\n"
            f"➡️ **{right_idol[1]}** ({right_idol[2]})\n\n"
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


def build_daily_round_embeds(left_idol, right_idol, bracket: BracketState) -> list[discord.Embed]:
    stage = bracket.round_label()
    match_num = bracket.total_matches_played + 1
    header = discord.Embed(
        title=f"🌟 Daily Bracket — {stage} ({match_num}/7)",
        description=(
            f"⬅️ **{left_idol[1]}** ({left_idol[2]})\n"
            f"➡️ **{right_idol[1]}** ({right_idol[2]})\n\n"
            "Vote for your bias!"
        ),
        color=discord.Color.gold(),
        url=_EMBED_GROUP_URL,
    )
    if left_idol[4]:
        header.set_image(url=left_idol[4])

    right = discord.Embed(url=_EMBED_GROUP_URL)
    if right_idol[4]:
        right.set_image(url=right_idol[4])

    return [header, right]


def build_daily_summary_embed(
    matchups: list[MatchupLog],
    champion,
    voter_name: str | None = None,
    voter_icon_url: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="🌟 Daily Bias Bracket",
        description=f"🏆 **{champion[1]}** ({champion[2]}) takes the crown!",
        color=discord.Color.gold(),
    )
    if voter_name:
        embed.set_author(name=voter_name, icon_url=voter_icon_url)
    if champion[4]:
        embed.set_image(url=champion[4])

    lines = []
    for i, log in enumerate(matchups, 1):
        if log.winner_idx == 0:
            l_disp = f"**{log.left_name}**"
            r_disp = f"{log.right_name}"
        else:
            l_disp = f"{log.left_name}"
            r_disp = f"**{log.right_name}**"
        lines.append(f"**{i}.** {l_disp} vs {r_disp}")
    if lines:
        embed.add_field(name="Matches", value="\n".join(lines), inline=False)

    embed.set_footer(text="Run `/bias leaderboard` to see your updated bias list!")
    return embed


def build_leaderboard_embeds(
    title: str, tops: list[tuple[str, str, str, int, str]]
) -> list[discord.Embed]:
    """Header embed with the ranked list + #1 image, plus gallery embeds for #2 and #3."""
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    lines = []
    for rank, (_, name, group, elo, image_url) in enumerate(tops, 1):
        prefix = medals.get(rank, f"**#{rank}**")
        lines.append(f"{prefix}  **{name}** · {group} — **{elo}**")

    header = discord.Embed(
        title=f"🏆 {title}",
        description="\n".join(lines) if lines else "No entries yet.",
        color=discord.Color.gold(),
        url=_EMBED_GROUP_URL,
    )
    if tops and tops[0][4]:
        header.set_image(url=tops[0][4])

    embeds = [header]
    for rank in (2, 3):
        if len(tops) >= rank and tops[rank - 1][4]:
            podium = discord.Embed(url=_EMBED_GROUP_URL)
            podium.set_image(url=tops[rank - 1][4])
            embeds.append(podium)

    return embeds


def build_result_embed(selected, unselected, pw: int, pl: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"You chose {selected[1]}!",
        description=f"**{selected[1]}** ({selected[2]}) over {unselected[1]} ({unselected[2]})",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="Personal Bias Score", value=f"Selected: +{pw} | Unselected: {pl}", inline=False
    )
    if selected[4]:
        embed.set_image(url=selected[4])
    return embed


class VoteView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        guild_id: int,
        matchup,
        current_round: int = 1,
        matchups_log: list[MatchupLog] | None = None,
        bracket: BracketState | None = None,
    ):
        super().__init__(timeout=30.0)
        self.user_id = user_id
        self.guild_id = guild_id
        self.current_round = current_round
        self.matchups_log = matchups_log or []
        self.bracket = bracket

        self.left_idol, self.right_idol = matchup[0], matchup[1]

        # Personalize the vote buttons so the user sees whose face they're picking
        # (the decorator-defined labels get overwritten on each instance).
        self.left_button.label = f"{self.left_idol[1]}"
        self.right_button.label = f"{self.right_idol[1]}"

        # Daily bracket uses gold styling and hides the bail-out buttons so
        # users have to vote every match to earn completion credit.
        if self.is_daily:
            self.embeds = build_daily_round_embeds(self.left_idol, self.right_idol, self.bracket)
            self.remove_item(self.skip_button)
            self.remove_item(self.end_button)
        else:
            self.embeds = build_round_embeds(self.left_idol, self.right_idol, self.current_round)

    @property
    def is_daily(self) -> bool:
        return self.bracket is not None

    @classmethod
    async def create(
        cls,
        user_id: int,
        guild_id: int,
        current_round: int = 1,
        matchups_log: list[MatchupLog] | None = None,
    ) -> "VoteView":
        # Matchup fetch hits the DB, keep it off the event loop
        matchup = await asyncio.to_thread(get_matchup, user_id)
        if not matchup:
            raise ValueError("Not enough idols to match up!")
        return cls(user_id, guild_id, matchup, current_round, matchups_log)

    @classmethod
    async def create_daily(cls, user_id: int, guild_id: int) -> "VoteView":
        idols = await asyncio.to_thread(get_daily_idols)
        if len(idols) < 8:
            raise ValueError("Not enough active idols to run today's daily bracket.")
        bracket = BracketState(current_round_idols=list(idols))
        first_pair = bracket.current_pair()
        return cls(user_id, guild_id, first_pair, bracket=bracket)

    async def on_timeout(self) -> None:
        if getattr(self, "_answered", False):
            return

        for item in self.children:
            item.disabled = True

        if hasattr(self, "interaction"):
            try:
                if self.matchups_log:
                    summary_embed = VoteSummaryEmbed(
                        self.matchups_log,
                        voter_name=self.interaction.user.display_name,
                        voter_icon_url=self.interaction.user.display_avatar.url,
                    )
                    await self.interaction.channel.send(embed=summary_embed)
                    content = "Session timed out! Summary posted."
                else:
                    content = "Session timed out, likely discord issue! Start another session to continue!"

                await self.interaction.edit_original_response(
                    content=content,
                    embeds=[],
                    view=None,
                )
            except Exception:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your voting session!", ephemeral=True
            )
            return False

        if getattr(self, "_answered", False):
            # Already answered, quietly ack to avoid Discord showing "Interaction failed"
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except discord.errors.InteractionResponded:
                    pass
            return False

        self._answered = True
        return True

    async def process_vote(self, interaction: discord.Interaction, winner_idx: int):
        # Ack immediately so we don't trip Discord's 3s interaction deadline
        # while record_vote's sync DB work is running in a worker thread.
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except discord.errors.InteractionResponded:
                pass

        # 0 = left, 1 = right
        selected = self.left_idol if winner_idx == 0 else self.right_idol
        unselected = self.right_idol if winner_idx == 0 else self.left_idol

        # Disable buttons
        for item in self.children:
            item.disabled = True

        # Stop listening so the timeout timer is cancelled
        self.stop()

        # Process ELO (sync DB work pushed to a worker thread)
        gw, gl, sw, sl, pw, pl = await asyncio.to_thread(
            record_vote, self.user_id, self.guild_id, selected[0], unselected[0]
        )
        await asyncio.to_thread(add_stat_count, "bias_vote_cast")
        self.matchups_log.append(
            MatchupLog(
                left_name=self.left_idol[1],
                left_group=self.left_idol[2],
                right_name=self.right_idol[1],
                right_group=self.right_idol[2],
                winner_idx=winner_idx,
            )
        )
        if self.is_daily:
            self.bracket.record_winner(selected)

        # Collapse to a single result embed so the selected image gets the full frame
        self.embeds = [build_result_embed(selected, unselected, pw, pl)]
        await interaction.edit_original_response(embeds=self.embeds, view=self)

        await asyncio.sleep(1.5)
        await self._advance(interaction)

    async def _advance(self, interaction: discord.Interaction) -> None:
        """Hand off to the next round or emit the final summary.
        Assumes the interaction has already been deferred/ack'd."""
        if self.is_daily:
            await self._advance_daily(interaction)
            return

        next_view = await VoteView.create(
            self.user_id,
            self.guild_id,
            self.current_round + 1,
            self.matchups_log,
        )
        next_view.interaction = interaction
        await interaction.edit_original_response(embeds=next_view.embeds, view=next_view)

    async def _advance_daily(self, interaction: discord.Interaction) -> None:
        if self.bracket.is_complete():
            await asyncio.to_thread(record_daily_completion, self.user_id)
            await asyncio.to_thread(add_stat_count, "bias_daily_completed")
            summary = build_daily_summary_embed(
                self.matchups_log,
                self.bracket.champion(),
                voter_name=interaction.user.display_name,
                voter_icon_url=interaction.user.display_avatar.url,
            )
            await interaction.channel.send(embed=summary)
            await interaction.edit_original_response(
                content="Daily bracket complete — summary posted.",
                embeds=[],
                view=None,
            )
            return

        next_view = VoteView(
            self.user_id,
            self.guild_id,
            self.bracket.current_pair(),
            self.current_round + 1,
            self.matchups_log,
            bracket=self.bracket,
        )
        next_view.interaction = interaction
        await interaction.edit_original_response(embeds=next_view.embeds, view=next_view)

    @discord.ui.button(label="⬅️ Left", style=discord.ButtonStyle.primary)
    async def left_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 0)

    @discord.ui.button(label="➡️ Right", style=discord.ButtonStyle.primary)
    async def right_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 1)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except discord.errors.InteractionResponded:
                pass
        for item in self.children:
            item.disabled = True

        self.stop()
        await self._advance(interaction)

    @discord.ui.button(label="End", style=discord.ButtonStyle.secondary, emoji="🏁")
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except discord.errors.InteractionResponded:
                pass
        for item in self.children:
            item.disabled = True

        self.stop()

        if self.matchups_log:
            summary_embed = VoteSummaryEmbed(
                self.matchups_log,
                voter_name=interaction.user.display_name,
                voter_icon_url=interaction.user.display_avatar.url,
            )
            await interaction.channel.send(embed=summary_embed)
            content = "Session ended — summary posted."
        else:
            content = "Session ended."

        await interaction.edit_original_response(
            content=content,
            embeds=[],
            view=None,
        )
