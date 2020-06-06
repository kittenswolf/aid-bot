# -*- coding: utf-8 -*-

import logging
import time
import traceback
import inspect

import discord
from discord.ext import commands
from colorlog import ColoredFormatter

import config


class AIBot(commands.Bot):

    def __init__(self):
        self.create_logger()

        # Members are fetched after all attributes were set to speed up bot starting
        super().__init__(
            command_prefix=config.bot.command_prefix,
            fetch_offline_member=False,
            activity=discord.Game(name="Starting up...")
        )

        self.setup_cogs()

    def create_logger(self):
        """
        log.debug("A message only used for debugging")
        log.info("Curious devs might want to know this")
        log.warn("Something is wrong and the dev should be informed")
        log.error("Serious stuff, this is red for a reason")
        log.critical("OH NO everything is on fire")
        """

        formatter = ColoredFormatter("%(log_color)s%(asctime)s - %(levelname)-8s - %(message)s")
        stream = logging.StreamHandler()
        stream.setLevel(config.logging_level)
        stream.setFormatter(formatter)
        self.logger = logging.getLogger("bot")
        self.logger.addHandler(stream)
        self.logger.setLevel(config.logging_level)

    def get_error_code(self):
        """ Generates an error code. """

        number = int(time.time() * 10000000)
        alphabet, base36 = ['0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', '']
        while number:
            number, i = divmod(number, 36)
            base36 = alphabet[i] + base36
        return base36 or alphabet[0]

    def setup_cogs(self):
        self.remove_command("help")

        for cog_name in config.bot.startup_cogs:
            self.logger.debug(f"Loading {cog_name}...")
            try:
                self.load_extension(cog_name)

                for cog_name in self.cogs:
                    cog = self.get_cog(cog_name)

            except Exception as error:
                self.logger.error(error)
                traceback.print_exception(type(error), error, error.__traceback__)


    async def on_command_error(self, ctx, error):
        self.logger.error(f"{error}, type {type(error)}")

        ignore_error = [
            discord.ext.commands.errors.CommandNotFound,
            discord.ext.commands.errors.NoPrivateMessage,
            discord.ext.commands.errors.CheckFailure
        ]
        send_help = [
            discord.ext.commands.errors.BadArgument,
            discord.ext.commands.errors.MissingRequiredArgument,
            discord.ext.commands.errors.ExpectedClosingQuoteError,
            discord.ext.commands.errors.InvalidEndOfQuotedStringError
        ]
        no_dms = [discord.ext.commands.errors.NoPrivateMessage]
        cooldown_msg = [discord.ext.commands.CommandOnCooldown]
        perms_msg = [discord.ext.commands.errors.MissingPermissions]

        if type(error) in ignore_error:
            return

        if type(error) in perms_msg:
            await ctx.send("You do not have permissions to run this command!")
            return

        if type(error) in send_help:
            usage = inspect.getdoc(ctx.command.callback)

            if usage is not None:
                await ctx.send("```" + usage + "```")
            else:
                await ctx.send(f"```CSS\n(no help available)```")

            return

        if type(error) in cooldown_msg:
            await ctx.send(f"Relax! You need to wait `{error.retry_after:.2f}`s.")
            return

        if type(error) in no_dms:
            await ctx.send("You can only use this in servers.")
            return

        if "403 forbidden" in str(error).lower():
            await ctx.send("\n".join([
                ":x: **I'm missing at least one of the following permissions:**",
                "```",
                "- Send messages",
                "- Manage messages",
                "- Embed links",
                "- Add reactions",
                "```",
                "Please make sure I have sufficient permissions and try again."
            ]))
            return


        error_id = self.get_error_code()
        await ctx.send(f"An error occured! Error code: `{error_id}`. This event was logged and will be investigated.")

        self.logger.error(f"vvv An error occured: {error_id} vvv")
        traceback.print_exception(type(error), error, error.__traceback__)
        self.logger.error(f"^^^ An error occured: {error_id} ^^^")


    async def on_command(self, ctx):
        location_repr = ctx.guild.name if ctx.guild else "DMs"
        self.logger.debug(f"User {ctx.author} invoked the command '{ctx.message.content}' (Location: {location_repr})")


    async def on_ready(self):
        game = discord.Game(name=f"{config.bot.command_prefix}play to start | {config.bot.command_prefix}help for help")
        await self.change_presence(status=discord.Status.online, activity=game)

    def run(self):
        """ Loads the token and runs the bot. """

        # import logging
        # logging.basicConfig(level=logging.DEBUG)

        token = open("data/token.txt", "r").read()
        self.logger.info("Running...")
        super().run(token)

