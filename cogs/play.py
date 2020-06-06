# -*- coding: utf-8 -*-

import json
import asyncio
import pickle
import time
import random

import discord
from discord.ext import commands

import aiohttp
from faker import Faker
from faker.providers import internet

import config


class ServerOverloadedException(Exception):
    pass



def get_random_useragent():
    return random.choice([
        "Mozilla/5.0 (compatible; MSIE 10.0; Macintosh; Intel Mac OS X 10_7_3; Trident/6.0)",
        "Mozilla/5.0 (compatible; MSIE 8.0; Windows NT 6.1; Trident/4.0; GTB7.4; InfoPath.2; SV1; .NET CLR 3.3.69573; WOW64; en-US)",
        "Opera/9.80 (X11; Linux i686; U; ru) Presto/2.8.131 Version/11.11",
        "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.2 (KHTML, like Gecko) Chrome/22.0.1216.0 Safari/537.2",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_4) AppleWebKit/537.13 (KHTML, like Gecko) Chrome/24.0.1290.1 Safari/537.13",
        "Mozilla/5.0 (X11; CrOS i686 2268.111.0) AppleWebKit/536.11 (KHTML, like Gecko) Chrome/20.0.1132.57 Safari/536.11",
        "Mozilla/5.0 (Windows NT 6.2; Win64; x64; rv:16.0.1) Gecko/20121011 Firefox/16.0.1",
        "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:15.0) Gecko/20100101 Firefox/15.0.1",
        "Mozilla/5.0 (iPad; CPU OS 6_0 like Mac OS X) AppleWebKit/536.26 (KHTML, like Gecko) Version/6.0 Mobile/10A5355d Safari/8536.25",
    ])


class Session:
    def __init__(self, access_token):
        self.access_token = access_token

        self._headers = {
            'User-Agent': get_random_useragent(),
            'Accept': '*/*',
            'Accept-Language': 'en-US;q=0.7,en;q=0.3',
            'Content-Type': 'application/json',
            'X-Access-Token': self.access_token,
            'Origin': 'https://play.aidungeon.io',
            'Connection': 'keep-alive',
            'TE': 'Trailers'
        }

        self.session_id = None

        self.max_tries = 5

    def _create_session(self):
        return aiohttp.ClientSession(
            headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=15)
            # connector=aiohttp.TCPConnector(ssl=False, verify_ssl=False)
        )

    async def chose_story(self, story_mode, character_type, name, custom_prompt=None, tries=1):
        data = self._json_to_text({
            "storyMode": story_mode,
            "characterType": character_type,
            "name": name if custom_prompt is None else None,
            "customPrompt": custom_prompt,
            "promptId": None
        })

        try:
            async with self._create_session() as session:
                async with session.post("https://api.aidungeon.io/sessions", data=data) as r:
                    response = await r.json()
        except Exception:
            if tries > self.max_tries:
                raise ServerOverloadedException

            await asyncio.sleep(tries)
            return await self.chose_story(story_mode, character_type, name, custom_prompt=custom_prompt, tries=tries+1)

        try:
            self.session_id = response["id"]
        except TypeError:
            print("Error grabbing new story result")
            if tries > self.max_tries:
                raise ServerOverloadedException
            else:
                await asyncio.sleep(tries)
                return await self.chose_story(story_mode, character_type, name, custom_prompt=custom_prompt, tries=tries+1)

        return response

    async def input(self, text, tries=1):
        data = self._json_to_text({
            "text": text
        })

        try:
            async with self._create_session() as session:
                async with session.post(f"https://api.aidungeon.io/sessions/{self.session_id}/inputs", data=data) as r:
                    response = await r.json()
        except Exception:
            if tries > self.max_tries:
                raise ServerOverloadedException

            await asyncio.sleep(tries)
            return await self.input(text, tries=tries+1)

        try:
            result = response[-1]["value"]
            if len(result) == 0:
                raise TypeError

            return result
        except TypeError:
            print("Error grabbing input result")
            if tries > self.max_tries:
                raise ServerOverloadedException

            await asyncio.sleep(tries)
            return await self.input(text, tries=tries+1)

    def _json_to_text(self, json_data):
        return json.dumps(json_data, separators=(',', ':'))


async def get_access_token():
    headers = {
        'User-Agent': get_random_useragent(),
        'Accept': '*/*',
        'Accept-Language': 'en-US;q=0.7,en;q=0.3',
        'Content-Type': 'application/json',
        'X-Access-Token': 'null',
        'Origin': 'https://play.aidungeon.io',
        'Connection': 'keep-alive',
        'TE': 'Trailers',
    }

    fake = Faker()
    fake.add_provider(internet)

    random_email = fake.email()
    data = '{"email":"' + random_email + '"}'

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post("https://api.aidungeon.io/users", data=data) as r:
            response = await r.json()


    return response["accessToken"]



class PlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.invite_link = "FILL_IN_HERE"
        self.support_discord_server = "FILL_IN_HERE"

        self.channels_in_use = set()
        self.session_managers = {}
        self.channel_sessions = {}
        self.channels_loading_results = set()

        self._load_data()

    def channel_in_use(self, channel_id: int):
        return channel_id in self.channels_in_use

    def add_channel_in_use(self, channel_id: int):
        self.channels_in_use.add(channel_id)

    def remove_channel_in_use(self, channel_id: int):
        self.channels_in_use.remove(channel_id)

    def add_session_manager(self, channel_id, user_id):
        if channel_id in self.session_managers:
            self.session_managers[channel_id].add(user_id)
        else:
            self.session_managers[channel_id] = {user_id}

    def remove_session_manager(self, channel_id, user_id):
        if channel_id in self.session_managers:
            if user_id in self.session_managers[channel_id]:
                self.session_managers[channel_id].remove(user_id)
        else:
            self.session_managers[channel_id] = set()


    def _save_data(self):
        pickle.dump(self.channels_in_use, open("data/channels_in_use.p", "wb"))
        pickle.dump(self.session_managers, open("data/session_managers.p", "wb"))

        formatted_channel_sessions = {}
        for channel_id, session in self.channel_sessions.items():
            formatted_channel_sessions[channel_id] = {
                "access_token": session.access_token,
                "session_id": session.session_id
            }

        pickle.dump(formatted_channel_sessions, open("data/channel_sessions.p", "wb"))

    def _load_data(self):
        self.bot.logger.debug("Loading data....")
        try:
            self.channels_in_use = pickle.load(open("data/channels_in_use.p", "rb"))
        except (FileNotFoundError):
            pass

        try:
            self.session_managers = pickle.load(open("data/session_managers.p", "rb"))
        except (FileNotFoundError):
            pass

        try:
            formatted_channel_sessions = pickle.load(open("data/channel_sessions.p", "rb"))
        except (FileNotFoundError):
            pass
        else:
            for channel_id, data in formatted_channel_sessions.items():
                session = Session(data["access_token"])
                session.session_id = data["session_id"]
                self.channel_sessions[channel_id] = session


        # Remove unnessecary data
        # Remove channels from the session managers with no users
        new_session_managers = {}
        for channel_id, session_managers in self.session_managers.items():
            if len(session_managers) > 0:
                new_session_managers[channel_id] = session_managers
            else:
                print(channel_id, "no managers")

        self.session_managers = new_session_managers

        # Remove sessions with no managers
        new_channel_sessions = {}
        for channel_id, channel_session in self.channel_sessions.items():
            if channel_id in self.session_managers:
                new_channel_sessions[channel_id] = channel_session
            else:
                print(channel_id, "no managers so no session")

        self.channel_sessions = new_channel_sessions

        # Remove channels in use with no session attached
        new_channels_in_use = set()
        for channel_id in self.channels_in_use:
            if channel_id in self.channel_sessions:
                new_channels_in_use.add(channel_id)
            else:
                print(channel_id, "no session so not in use")

        self.channels_in_use = new_channels_in_use



    async def save_data(self):
        self.bot.logger.info("Saving data....")
        start = time.time()
        await self.bot.loop.run_in_executor(None, self._save_data)

        time_taken = time.time() - start
        self.bot.logger.info(f"Took {time_taken:0.2f}s to save data.")


    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        # Remove guild data when removed from a guild
        for channel in guild.channels:
            if channel.id in self.session_managers:
                del self.session_managers[channel.id]

            if channel.id in self.channels_in_use:
                self.channels_in_use.remove(channel.id)

            if channel.id in self.channel_sessions:
                del self.channel_sessions[channel.id]

            if channel.id in self.channels_loading_results:
                self.channels_loading_results.remove(channel.id)

        await self.save_data()


    @commands.command(name="invite")
    async def cmd_invite(self, ctx):
        embed = discord.Embed(description=f"[Invite this bot to other servers!]({self.invite_link})")
        await ctx.send(embed=embed)

    @commands.command(name="support")
    async def cmd_support(self, ctx):
        embed = discord.Embed(description=f"[Support server]({self.support_discord_server})")
        await ctx.send(embed=embed)


    @commands.guild_only()
    @commands.command(name="play")
    async def cmd_play(self, ctx):
        """play - Starts a new game session.

        Only one game session is allowed per channel. Use p!end to end the game session in a given channel.
        """

        channel_in_use = self.channel_in_use(ctx.channel.id)
        if channel_in_use:
            raise discord.ext.commands.errors.BadArgument


        self.add_channel_in_use(ctx.channel.id)
        self.add_session_manager(ctx.channel.id, ctx.author.id)

        await self.save_data()


        description_lines = [
            "**You created a new game in this channel.**",
            "",
            f"__{ctx.author.mention}, you'll be able to use these commands to control the session:__",
            f"**`{config.bot.command_prefix}start` - Start the game running in this channel.**",
            f"`{config.bot.command_prefix}add @user` - Add a user to the session.",
            f"`{config.bot.command_prefix}remove @user` - Remove a user from the session.",
            f"`{config.bot.command_prefix}end` - End the game running in this channel.",
            "",
            f"[Invite this bot to other servers!]({self.invite_link})",
            "",
            "Please note: this is an unofficial bot. If you like this, consider supporting the creators of the [original](https://aidungeon.io/) on [Patreon](https://www.patreon.com/AIDungeon)."
        ]

        description = "\n".join(description_lines)
        embed = discord.Embed(
            description=description
        )

        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(name="add")
    async def cmd_add_user(self, ctx, user: discord.member.Member):
        channel_in_use = self.channel_in_use(ctx.channel.id)
        if not channel_in_use:
            await ctx.send(f":x: There's no session in this channel. (Use `{config.bot.command_prefix}play` to start one)")
            return

        if not ctx.author.id in self.session_managers[ctx.channel.id] and not ctx.author.permissions_in(ctx.channel).ban_members:
            await ctx.send(":x: You are not allowed to do this! Ask someone who is already added to do this.")
            return

        if user.id in self.session_managers[ctx.channel.id]:
            await ctx.send(":x: This user was already added!")
            return

        if user.bot:
            await ctx.send(":x: You can't add bots!")
            return

        self.add_session_manager(ctx.channel.id, user.id)

        await self.save_data()

        await ctx.send(f"Added `{user.name}` to the session.")


    @commands.guild_only()
    @commands.command(name="remove")
    async def cmd_remove_user(self, ctx, user: discord.member.Member):
        channel_in_use = self.channel_in_use(ctx.channel.id)
        if not channel_in_use:
            await ctx.send(f":x: There's no session in this channel. (Use `{config.bot.command_prefix}play` to start one)")
            return

        if not ctx.author.id in self.session_managers[ctx.channel.id] and not ctx.author.permissions_in(ctx.channel).ban_members:
            await ctx.send(":x: You are not allowed to do this! Ask someone who is added to the session to do this.")
            return

        if user.id not in self.session_managers[ctx.channel.id]:
            await ctx.send(":x: This user is not added!")
            return

        if ctx.author.id == user.id:
            await ctx.send(":x: You can't remove yourself!")
            return

        if len(self.session_managers[ctx.channel.id]) == 1:
            await ctx.send(":x: This would remove everyone from this session. Instead, use `p!end`.")

        self.remove_session_manager(ctx.channel.id, user.id)

        await self.save_data()

        await ctx.send(f"Removed `{user.name}` from the session.")


    @commands.guild_only()
    @commands.command(name="start")
    async def cmd_start_game(self, ctx):
        channel_in_use = self.channel_in_use(ctx.channel.id)
        if not channel_in_use:
            await ctx.send(f":x: There's no session in this channel. (Use `{config.bot.command_prefix}play` to start one)")
            return

        if not ctx.author.id in self.session_managers[ctx.channel.id] and not ctx.author.permissions_in(ctx.channel).ban_members:
            await ctx.send(":x: You are not allowed to do this! Ask someone who is added to the session to do this.")
            return

        # Pick story mode
        description_lines = [
            "**What is the story mode?**",
            "",
            ":one: fantasy",
            ":two: mystery",
            ":three: apocalyptic",
            ":four: zombies",
            ":five: custom",
            "",
            "Add a reaction to pick a story mode."
        ]
        description = "\n".join(description_lines)
        embed = discord.Embed(description=description)
        sent = await ctx.send(embed=embed)

        for i in range(1, 6):
            await sent.add_reaction('{}\u20e3'.format(i))


        def check(reaction, user):
            allowed_reactions = ['{}\u20e3'.format(i) for i in range(1, i + 1)]
            return (
                str(reaction.emoji) in allowed_reactions and
                user.id == ctx.author.id and
                reaction.message.id == sent.id
            )


        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=120, check=check)
        except asyncio.TimeoutError:
            await sent.clear_reactions()
            await ctx.send("Too slow. Try again.")
            return

        await sent.clear_reactions()


        story_mode_index = int(str(reaction).split("\u20e3")[0])
        
        story_mode_name = {
            1: "fantasy",
            2: "mystery",
            3: "apocalyptic",
            4: "zombies",
            5: "custom"
        }[story_mode_index]

        if story_mode_name == "custom":
            description_lines = [
                "**Custom Story Mode**",
                "",
                "Enter a prompt that describes who you are and the first couple sentences of where you start out.",
                "Example: `You are a knight in the kingdom of Larion. You are hunting the evil dragon who has been terrorizing the kingdom. You enter the forest searching for the dragon and see`"
            ]
            description = "\n".join(description_lines)
            embed = discord.Embed(description=description)
            custom_story_prompt = await sent.edit(embed=embed)

            def check(message):
                return (
                    message.author.id == ctx.author.id and
                    message.channel.id == sent.channel.id and
                    not message.clean_content.startswith(config.bot.command_prefix) and
                    self.channel_in_use(message.channel.id)
                )

            try:
                custom_prompt_message = await self.bot.wait_for("message", timeout=120, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"Too slow, try again. (`{config.bot.command_prefix}start`)")
                return

            character_name = None
            custom_prompt = custom_prompt_message.clean_content
        else:

            # Pick character
            character_options = {
                "fantasy": [
                    "noble",
                    "knight",
                    "squire",
                    "wizard",
                    "ranger",
                    "peasant",
                    "rogue"
                ],
                "mystery": [
                    "patient",
                    "detective",
                    "spy"
                ],
                "apocalyptic": [
                    "soldier",
                    "scavenger",
                    "survivor",
                    "courier"
                ],
                "zombies": [
                    "soldier",
                    "survivor",
                    "scientist"
                ]
            }[story_mode_name]


            description_lines = [
                "**Who are you playing?**",
                ""
            ]

            i = 1
            for character_option in character_options:
                line = f"{i}\u20e3 {character_option}"
                description_lines.append(line)

                i += 1

            description_lines.append("\nAdd a reaction to pick your character.")

            description = "\n".join(description_lines)
            embed = discord.Embed(description=description)
            await sent.edit(embed=embed)

            for i in range(1, i):
                await sent.add_reaction('{}\u20e3'.format(i))


            def check(reaction, user):
                allowed_reactions = ['{}\u20e3'.format(e) for e in range(1, i + 1)]
                return (
                    str(reaction.emoji) in allowed_reactions and
                    user.id == ctx.author.id and
                    reaction.message.id == sent.id
                )


            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=120, check=check)
            except asyncio.TimeoutError:
                await sent.clear_reactions()
                await ctx.send("Too slow. Try again.")
                return

            character_index = int(str(reaction).split("\u20e3")[0])
            character_name = character_options[character_index - 1]

            custom_prompt = None


        # Done, load access token

        if custom_prompt is None:
            embed = discord.Embed(description=f"Story mode: **{story_mode_name}**\nCharacter: **{character_name}**\nLoading, please wait...")
        else:
            embed = discord.Embed(description=f"Story mode: **Custom**\nLoading, please wait...")

        loading_indicator = await ctx.send(embed=embed)


        access_token = await get_access_token()
        self.bot.logger.debug(f"Created access token {access_token}")

        session = Session(access_token)
        self.channel_sessions[ctx.channel.id] = session


        try:
            if custom_prompt is not None:
                story_start = await self.channel_sessions[ctx.channel.id].chose_story(story_mode_name, character_name, ctx.author.name, custom_prompt=custom_prompt)
            else:
                story_start = await self.channel_sessions[ctx.channel.id].chose_story(story_mode_name, character_name, ctx.author.name)
        except ServerOverloadedException:
            new_embed = discord.Embed(description="*Sorry, it seems like the servers are overloaded. Try again?*")
            await loading_indicator.edit(embed=new_embed)
            return


        await self.save_data()

        description_lines = ["a" * 2050]
        max_story_chars = 2048
        while len("\n".join(description_lines)) > 2048:
            description_lines = [
                "**You started the game!**",
                "~~========================~~",
                story_start["story"][0]["value"][:max_story_chars],
                "~~========================~~",
                "",
                "Type `> do action` to do an action (ex. `> run away`)",
                "Type `!event` to indicate an event (ex. `!a strange man appears`)",
                'Type `"speech"` to indicate that you say something (ex. `"We should work together!"`)',
                "",
                f"__{ctx.author.mention}, you'll be able to use these commands to control the session:__",
                f"`{config.bot.command_prefix}add @user` - Add a user to the session.",
                f"`{config.bot.command_prefix}remove @user` - Remove a user from the session.",
                f"`{config.bot.command_prefix}end` - End the game running in this channel.",
            ]

            max_story_chars -= 1

        description = "\n".join(description_lines)
        embed = discord.Embed(
            description=description
        )

        await loading_indicator.edit(embed=embed)



    @commands.guild_only()
    @commands.command(name="end")
    async def cmd_end_game(self, ctx):
        channel_in_use = self.channel_in_use(ctx.channel.id)
        if not channel_in_use:
            await ctx.send(f":x: There's no session in this channel. (Use `{config.bot.command_prefix}play` to start one)")
            return

        if not ctx.author.id in self.session_managers[ctx.channel.id] and not ctx.author.permissions_in(ctx.channel).ban_members:
            await ctx.send(":x: You are not allowed to do this! Ask someone who is added to the session to do this.")
            return

        self.remove_channel_in_use(ctx.channel.id)

        if ctx.channel.id in self.channel_sessions:
            del self.channel_sessions[ctx.channel.id]

        if ctx.channel.id in self.session_managers:
            del self.session_managers[ctx.channel.id]


        await self.save_data()

        await ctx.send(f"Ended this session. To start another, type `{config.bot.command_prefix}play`")


    @commands.command(name="help")
    async def cmd_help(self, ctx):
        help_lines = [
            "**__Help__**",
            "__Guild only:__",
            f"`{config.bot.command_prefix}play` - Create a new session in this channel",
            f"`{config.bot.command_prefix}start` - Start the session and pick a story mode.",
            f"`{config.bot.command_prefix}end` - Ends the session running in this channel.",
            f"`{config.bot.command_prefix}add [@user]` - Add a user to the session in this channel.",
            f"`{config.bot.command_prefix}remove [@user]` - Remove a user from the session in this channel.",
            "",
            f"`{config.bot.command_prefix}invite` - [Invite this bot to other servers!]({self.invite_link})",
            f"`{config.bot.command_prefix}support` - [Join the support server]({self.support_discord_server})",
            "",
            "__Control the story:__",
            "Type `> do action` to do an action (ex. `> run away`)",
            "Type `!event` to indicate an event (ex. `!a strange man appears`)",
            'Type `"speech"` to indicate that you say something (ex. `"We should work together!"`)',
        ]

        embed = discord.Embed(description="\n".join(help_lines))
        await ctx.send(embed=embed)


    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.channel.id in self.channel_sessions:
            return

        if not message.author.id in self.session_managers[message.channel.id]:
            return


        # Replace typographic quotes with "real" ones
        message_content = message.clean_content.replace(u'\u201c', '"').replace(u'\u201d', '"')

        if not (message_content.startswith(">") or message_content.startswith("!") or message_content.startswith('"')):
            return

        if message.channel.id in self.channels_loading_results:
            embed = discord.Embed(description="*Sorry, only one message can be processed at a time.*")
            await message.channel.send(embed=embed)
            return


        if not message_content.startswith('"'):
            message_content = message_content.replace(">", "", 1).replace("!", "").strip()

        if message_content.lower().startswith("/revert") or message_content.lower().startswith("/alter"):
            return


        self.channels_loading_results.add(message.channel.id)
        try:
            embed = discord.Embed(description="Loading...")
            sent = await message.channel.send(embed=embed)

            try:
                result = await self.channel_sessions[message.channel.id].input(message_content)
            except ServerOverloadedException:
                result = "*Sorry, it seems like the servers are overloaded. Try again?*"


            if random.random() < 0.3:
                result += "\n\n*Please note: this is an unofficial bot. If you like this, consider supporting the creators of the [original](https://aidungeon.io/) on [Patreon](https://www.patreon.com/AIDungeon).*"
            else:
                if random.random() < 0.3:
                    result += f"\n\n*[Invite this bot to other servers!]({self.invite_link})*"


            embed = discord.Embed(description=result)

            if random.random() < 0.3:
                footer_text = random.choice([
                    "If the story seems to be stuck in a loop, try ending and starting another session.",
                    "Try setting a custom story mode!",
                    f"Want to submit a bug, feedback or question? - type {config.bot.command_prefix}support"
                ])
                embed.set_footer(text=footer_text)


            await sent.edit(embed=embed)

            self.channels_loading_results.remove(message.channel.id)

            self.bot.logger.debug(f"User {message.author} prompted `{message_content}`, resulted in `{result}`")
        except Exception as e:
            self.bot.logger.error(f"Error in message try - {e}")
            embed = discord.Embed(description="*Sorry, it seems like the servers are overloaded. Try again?*")

            try:
                await sent.edit(embed=embed)
            except Exception:
                pass

            try:
                self.channels_loading_results.remove(message.channel.id)
            except Exception:
                pass


def setup(bot):
    bot.add_cog(PlayCog(bot))
