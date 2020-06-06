# -*- coding: utf-8 -*-

import discord
from discord.ext import commands

import config



class LogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.logger.info(f"I am in {len(self.bot.guilds)} guilds.")

        total_member_count = sum([guild.member_count for guild in self.bot.guilds])
        self.bot.logger.info(f"Total members: {total_member_count}")

        sorted_guilds_by_member_count = list(sorted(self.bot.guilds, key=lambda guild: guild.member_count, reverse=True))

        index = 1
        for guild in sorted_guilds_by_member_count[:10]:
            self.bot.logger.debug(f"{index}. '{guild.name}', {guild.member_count} members")
            index += 1


    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        self.bot.logger.info(f"Joined the guild '{guild.name}'")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        self.bot.logger.info(f"Left the guild '{guild.name}'")


def setup(bot):
    bot.add_cog(LogCog(bot))
