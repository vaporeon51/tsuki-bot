#!/usr/bin/env python3
"""List the Discord servers this bot is in, or make it leave one.

Examples:
    python scripts/manage_guilds.py list
    python scripts/manage_guilds.py leave 123456789012345678 --yes

The script loads TOKEN (or DISCORD_TOKEN) from the repository's .env file.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("list", help="List every server the bot is in.")

    leave_parser = subcommands.add_parser("leave", help="Make the bot leave a server.")
    leave_parser.add_argument("guild_id", type=int, help="The server ID to leave.")
    leave_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that the bot should leave the specified server.",
    )
    return parser.parse_args()


class GuildManager(discord.Client):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__(intents=discord.Intents.default())
        self.args = args
        self.failure: RuntimeError | None = None

    async def on_ready(self) -> None:
        try:
            if self.args.command == "list":
                self.list_guilds()
            else:
                await self.leave_guild(self.args.guild_id)
        except RuntimeError as error:
            self.failure = error
        finally:
            await self.close()

    def list_guilds(self) -> None:
        if not self.guilds:
            print("The bot is not in any servers.")
            return

        print(f"The bot is in {len(self.guilds)} server(s):")
        for guild in sorted(
            self.guilds,
            key=lambda item: item.member_count if item.member_count is not None else -1,
            reverse=True,
        ):
            member_count = guild.member_count if guild.member_count is not None else "unknown"
            print(
                f"- {guild.name}\n"
                f"  ID: {guild.id}\n"
                f"  Members: {member_count}\n"
                f"  Owner user ID: {guild.owner_id}"
            )

    async def leave_guild(self, guild_id: int) -> None:
        guild = self.get_guild(guild_id)
        if guild is None:
            available_ids = ", ".join(str(item.id) for item in self.guilds) or "none"
            raise RuntimeError(f"The bot is not in server {guild_id}. Available IDs: {available_ids}")

        if not self.args.yes:
            raise RuntimeError(
                f"Refusing to leave '{guild.name}' ({guild.id}) without --yes. "
                "Run the command again with --yes to confirm."
            )

        await guild.leave()
        print(f"Left '{guild.name}' ({guild.id}).")


def main() -> None:
    args = parse_args()
    if args.command == "leave" and not args.yes:
        sys.exit("Error: Add --yes to confirm that the bot should leave the specified server.")

    token = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")
    if not token:
        sys.exit("Set TOKEN or DISCORD_TOKEN in .env or the environment.")

    client = GuildManager(args)
    client.run(token)
    if client.failure is not None:
        sys.exit(f"Error: {client.failure}")


if __name__ == "__main__":
    main()
