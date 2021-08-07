import os
import re
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Any, List, Optional, Tuple, Union

import discord
from discord import Embed, Intents, Colour
from discord.ext.tasks import loop
from discord.ext.commands import Bot, Cog, DefaultHelpCommand, command
from dotenv import load_dotenv


ADTRAN_BLURPLE = (66, 89, 155)
STR_LENGTH = 62
MIDNIGHT_JAN1 = 1609459200.0
DAYS_TO_SECONDS = 86400
ICON_PATH = Path(__file__).parent / "icon.jpg"
EMOJIS_PATH = Path(__file__).parent / "emojis"
ALTERS_PATH = Path(__file__).parent / "avatars"
ALTERS = [("Tom Stanton", "tom.png"), ("Becky Hacker", "becky.png")]
CONFIG_OPTIONS = ["bot", "important", "teatime", "mod-bot", "games"]
CONFIG_PATH = Path(__file__).parent / "config.json"
SCHEDULED = {"timecard": (651600, 1209600), "teatime": (75600, 86400, (0, 4))}

with open(CONFIG_PATH) as config_file:
    config = json.load(config_file)


def dm_only(ctx):
    return not bool(ctx.guild)


def guild_only(ctx):
    return bool(ctx.guild)


def bot_only(ctx):
    return bool(ctx.guild) and ctx.channel.id == config["guilds"][str(ctx.guild.id)]["bot"]


def mod_only(ctx):
    return bool(ctx.guild) and ctx.channel.id == config["guilds"][str(ctx.guild.id)]["mod-bot"]


def update_config():
    global config
    with open(CONFIG_PATH, "w") as config_update:
        json.dump(config, config_update, indent=4)


async def send_msg(
    ctx,
    title: Optional[str] = Embed.Empty,
    description: Optional[Union[list, str]] = Embed.Empty,
    footer: Optional[str] = Embed.Empty,
    channel: discord.TextChannel = None,
    wrap: bool = True,
):
    if channel is None:
        channel = ctx.channel
    if type(description) == list:
        description = "\n".join([line.ljust(STR_LENGTH) for line in description])
    elif type(description) == str:
        description = description.ljust(STR_LENGTH)
    if wrap:
        description = "```" + description + "```"
    msg = await channel.send(
        embed=Embed(title=title, description=description, colour=Colour.from_rgb(*ADTRAN_BLURPLE)).set_footer(
            text=footer
        )
    )
    return msg


async def next_scheduled(offset: float, repeat: float, day_range: Optional[Tuple[int, int]] = None):
    benchmark = float(MIDNIGHT_JAN1 + offset)
    while benchmark < datetime.now().timestamp() or (
        day_range is not None and not (day_range[0] <= datetime.fromtimestamp(benchmark).weekday() <= day_range[1])
    ):
        benchmark += repeat
    return datetime.fromtimestamp(benchmark)


async def find_member(ctx, name: str):
    member = ctx.guild.get_member_named(name)
    if not member:
        if name.startswith("<@!"):
            member = ctx.guild.get_member(int(name[3:-1]))
            if member is not None:
                return member
            else:
                await send_msg(ctx, title="Find User Error", description=f"No member found with the id {name[3:-1]}")
                return None
        members = [
            member
            for member in ctx.guild.members
            if name.lower() in member.name.lower() or (member.nick and name.lower() in member.nick.lower())
        ]
        if len(members) == 0:
            await send_msg(ctx, title="Find User Error", description=f"No member found with the name {name}")
            return None
        elif len(members) > 1:
            await send_msg(ctx, title="Find User Error", description=f"Too many members found with the name {name}")
            return None
        else:
            member = members[0]
    return member


async def reaction_menu(ctx, title: str, options: List[Tuple[str, Any]], icons: List[str] = None):
    if icons is None:
        icons = [
            "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT TWO}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT THREE}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT FOUR}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT FIVE}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT SIX}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT SEVEN}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT EIGHT}\N{COMBINING ENCLOSING KEYCAP}",
            "\N{DIGIT NINE}\N{COMBINING ENCLOSING KEYCAP}",
            "🔟",
            "🔴",
            "🟠",
            "🟡",
            "🟢",
            "🔵",
            "🟣",
            "🟤",
            "⚫",
            "⚪",
        ]
    description = []
    for i, option in enumerate(options):
        description.append(f"{icons[i]} : {options[i][0]}")
    msg = await send_msg(ctx, title=title, description="\n".join(description), wrap=False)
    for i, _ in enumerate(options):
        await msg.add_reaction(icons[i])

    def check_react(reaction, author):
        if reaction.message.id != msg.id:
            return False
        if author != ctx.message.author:
            return False
        if str(reaction.emoji) not in icons:
            return False
        return True

    try:
        response, member = await ctx.bot.wait_for("reaction_add", check=check_react, timeout=120)
    except Exception as e:
        print(e)
        await msg.delete()
        await send_msg(
            ctx,
            title="Timeout Reached",
            description="The timeout of two minutes has been reached, please retry the command",
        )
    else:
        await msg.delete()
        i = icons.index(response.emoji)
        return options[i][1]


async def text_menu(ctx, title: str, description: str, re_string: str):
    def check_text(message):
        if message.channel.id != msg.channel.id:
            return False
        if message.author != ctx.message.author:
            return False
        return True

    match, count = None, 0
    while match is None and count < 3:
        try:
            msg = await send_msg(ctx, title=title, description=description)
            response = await ctx.bot.wait_for("message", check=check_text, timeout=300)
        except Exception as e:
            print(e)
            await msg.delete()
            if bool(ctx.guild):
                await response.delete()
            await send_msg(
                ctx,
                title="Timeout Reached",
                description="The timeout of two minutes has been reached, please retry the command",
            )
            return
        else:
            await msg.delete()
            if bool(ctx.guild):
                await response.delete()
            count += 1
            match = re.match(re_string, response.content)
    if match:
        return match.group(0)
    else:
        await send_msg(
            ctx,
            title="Text Input Failed",
            description="Text has not been successfully inputed after three tries, please retry the command",
        )


class Owner(Cog, description="The owner commands available to you"):
    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        return ctx.bot.is_owner(ctx.author)

    @command(
        checks=[dm_only],
        brief="View a list of guilds",
        description="View a list of guilds that the bot is active in",
    )
    async def guilds(self, ctx):
        await send_msg(ctx, title="Active Guilds", description=[guild.name for guild in ctx.bot.guilds])

    @command(
        checks=[dm_only],
        brief="Generate an invite",
        description="Generate an invite to an existing server",
    )
    async def invite(self, ctx):
        inv_guild = await reaction_menu(
            ctx, title="Select A Guild To Join", options=[(guild.name, guild) for guild in ctx.bot.guilds]
        )
        if inv_guild:
            await ctx.channel.send(await inv_guild.system_channel.create_invite())

    @command(
        checks=[dm_only],
        brief="Delete a guild",
        description="Delete a guild that the bot has control over",
    )
    async def delguild(self, ctx):
        del_guild = await reaction_menu(
            ctx, title="Select A Guild To Delete", options=[(guild.name, guild) for guild in ctx.bot.guilds]
        )
        if del_guild:
            confirm = await reaction_menu(
                ctx,
                title=f"Confirm {del_guild.name} Deletion",
                options=[("Yes, delete", True), ("No, don't delete", False)],
            )
            if confirm:
                await del_guild.delete()
                await send_msg(ctx, title="Guild Deleted", description=f"{del_guild.name} has been deleted")
                config["guilds"].pop(str(del_guild.id))
                update_config()
            else:
                await send_msg(
                    ctx, title="Cancelled Guild Deletion", description=f"{del_guild.name} has not been deleted"
                )

    @command(
        checks=[bot_only],
        brief="Demote someone from mod",
        description="Demote someone from mod to prevent access to bot features",
    )
    async def demote(self, ctx, name):
        demote_member = await find_member(ctx, name)
        if demote_member:
            await demote_member.remove_roles(ctx.guild.get_role(config["guilds"][str(ctx.guild.id)]["mod"]))
            name = demote_member.nick if demote_member.nick else demote_member.name
            await send_msg(ctx, title="Member Demoted", description=f"{name} has been demoted from mod")


class Admin(Cog, description="The admin commands available to you"):
    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        return bool(ctx.guild) and (
            ctx.bot.is_owner(ctx.author)
            or ctx.guild.get_role(config["guilds"][str(ctx.guild.id)]["mod"]) in ctx.author.roles
        )

    @Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")

    @Cog.listener()
    async def on_member_join(self, member):
        if await self.bot.is_owner(member):
            admin_role = member.guild.get_role(config["guilds"][str(member.guild.id)]["admin"])
            await member.add_roles(admin_role)
            await member.send(
                embed=Embed(
                    title="Owner Status Detected",
                    description=f"You are the owner, this will be represented in {member.guild.name}",
                    colour=Colour.from_rgb(*ADTRAN_BLURPLE),
                )
            )
        else:
            if member.id in config["mods"]:
                mod_role = member.guild.get_role(config["guilds"][str(member.guild.id)]["mod"])
                await member.add_roles(mod_role)
                await member.send(
                    embed=Embed(
                        title="Mod Status Detected",
                        description=f"You have been set as a mod, this will be represented in {member.guild.name}\nRun !help in both bot-hell and mod-commands as you can run different commands in each channel",
                    )
                )
            config["members"][str(member.id)] = member.guild.id
            update_config()
            await member.send(
                embed=Embed(
                    title="Welcome to the Co-op Discord Server!",
                    description=f"You have recently joined {member.guild.name}. When you are ready to register, please respond with `!register`",
                    colour=Colour.from_rgb(*ADTRAN_BLURPLE),
                )
            )
            register_role = member.guild.get_role(config["guilds"][str(member.guild.id)]["register"])
            await member.add_roles(register_role)

    @Cog.listener()
    async def on_guild_join(self, guild):
        if len(guild.roles) == 1:
            bot_role = await guild.create_role(name="Tom Stanton", hoist=True, colour=Colour.from_rgb(*ADTRAN_BLURPLE))
            await guild.me.add_roles(bot_role)

    @command(
        checks=[mod_only],
        brief="Allow a member to reregister",
        description="Allow a member to reregister and reset their info",
    )
    async def rereg(self, ctx, name: str):
        rereg_member = await find_member(ctx, name)
        if rereg_member:
            rem_roles = [role for role in rereg_member.roles if role.name != "@everyone" and role.name != "Admin" and role.name != "Mod" and role.name != ctx.bot.user.name]
            if len(rem_roles) == 0:
                return
            else:
                await rereg_member.remove_roles(*rem_roles)
                register_role = ctx.guild.get_role(config["guilds"][str(ctx.guild.id)]["register"])
                await rereg_member.add_roles(register_role)
                config["members"][str(rereg_member.id)] = ctx.guild.id
                await rereg_member.send(
                    embed=Embed(
                        title="Reregister Allowed",
                        description=f"You have been allowed to reregister for {rereg_member.guild.name}. When you are ready to register, please respond with `!register`",
                        colour=Colour.from_rgb(*ADTRAN_BLURPLE),
                    )
                )
                await send_msg(
                    ctx,
                    title="Reregister Successful",
                    description=f"{rereg_member.nick} has been set to reregister"
                )

    @command(
        checks=[bot_only],
        brief="Change the alter",
        description="Change the alter to another name/avatar",
    )
    async def alter(self, ctx):
        alter = await reaction_menu(
            ctx,
            title="Select a new alter",
            options=[(alter[0], i) for i, alter in enumerate(ALTERS)]
        )
        if alter is None:
            return
        if ALTERS[alter][0].split(" ")[0] == ctx.bot.user.name.split(" ")[0]:
            await send_msg(
                ctx,
                title="Alter Error",
                description="The alter you have selected is already in use"
            )
            return
        else:
            with open(ALTERS_PATH / ALTERS[alter][1], "rb") as avatar:
                avatar = avatar.read()
            await ctx.bot.user.edit(username=ALTERS[alter][0], avatar=avatar)
            await send_msg(
                ctx,
                title="Alter Updated",
                description=f"The bot alter has been updated to {ALTERS[alter][0]}"
            )

    @command(
        checks=[bot_only],
        brief="Add a new emoji",
        description="Add a new emoji by commenting an uploaded image with !emoji <name>",
    )
    async def emoji(self, ctx, emoji_name):
        if len(ctx.message.attachments) == 0:
            await send_msg(
                ctx, title="Emoji Error", description="!emoji <name> must be used when commenting on an uploaded emoji"
            )
        elif len(ctx.message.attachments) == 1:
            emoji_file = ctx.message.attachments[0]
            emoji_file = await emoji_file.to_file()
            emoji_file = emoji_file.fp.read()
            await ctx.guild.create_custom_emoji(name=emoji_name, image=emoji_file)
            with open(EMOJIS_PATH / f"{emoji_name}.jpg", "wb") as new_emoji_file:
                new_emoji_file.write(emoji_file)
        else:
            await send_msg(ctx, title="Emoji Error", description="Multiple emoji files cannot be uploaded at once")

    @command(
        checks=[bot_only],
        brief="Change the bot nickname",
        description='Change the bot nickname to match the form First "Nick" Last',
    )
    async def botnick(self, ctx, nickname=None):
        if '"' in ctx.bot.user.name:
            basename = ctx.bot.user.name.split('"')[0][:-1] + " " + ctx.bot.user.name.split('"')[-1][1:]
        else:
            basename = ctx.bot.user.name
        if nickname is None:
            await ctx.bot.user.edit(username=basename)
            await send_msg(ctx, title="Nickname Reset", description=f"The bot nickname has been reset")
        elif '"' in nickname:
            await send_msg(ctx, title="Nickname Error", description="The bot nickname cannot contain '\"'")
        else:
            if len(basename) + len(nickname) + 3 > 32:
                await send_msg(
                    ctx, title="Nickname Error", description="The bot nickname cannot be longer than 32 characters"
                )
            else:
                nickname = basename.split()[0] + ' "' + nickname + '" ' + basename.split()[1]
                await ctx.bot.user.edit(username=nickname)
                await send_msg(ctx, title="Nickname Changed", description=f"The bot is now {nickname}")

    @command(
        checks=[guild_only],
        brief="Configure bot channels",
        description=f"Configure bot channels with the options {CONFIG_OPTIONS}",
    )
    async def config(self, ctx, channel):
        channel = channel.lower()
        if channel not in CONFIG_OPTIONS:
            await send_msg(ctx, title="Config Error", description=f"Config option must be in {CONFIG_OPTIONS}")
        else:
            config["guilds"][str(ctx.guild.id)][channel] = ctx.channel.id
            update_config()
            await send_msg(
                ctx, title="Config Successful", description=f"{ctx.channel.name} has been set as the {channel} channel"
            )

    @command(
        checks=[mod_only],
        brief="Create a new text channel",
        description="Create a new text channel in the Text Channels category",
    )
    async def newchannel(self, ctx, channel: str):
        categories = await ctx.guild.fetch_channels()
        new_channel = await ctx.guild.create_text_channel(channel, category=categories[0], position=2)
        await send_msg(
            ctx, title="Channel Created", description=f"{new_channel.name} has been created under Text Channels"
        )

    @command(
        checks=[mod_only],
        brief="Promote someone to mod",
        description="Promote someone to mod to provide access to bot features",
    )
    async def promote(self, ctx, name):
        promote_member = await find_member(ctx, name)
        if promote_member:
            await promote_member.add_roles(ctx.guild.get_role(config["guilds"][str(ctx.guild.id)]["mod"]))
            name = promote_member.nick if promote_member.nick else promote_member.name
            await send_msg(ctx, title="Member Promoted", description=f"{name} has been promoted to mod")

    @command(
        checks=[mod_only],
        brief="Create a new co-op discord server",
        description="Create a new co-op discord server and set it up with the bot",
    )
    async def newguild(self, ctx):
        # Setup Information
        year = int(datetime.now().strftime("%Y"))
        year = await reaction_menu(
            ctx,
            title="Select the year of the new co-op server",
            options=[(str(year), str(year)), (str(year + 1), str(year + 1))],
        )
        if not year:
            return
        semester = await reaction_menu(
            ctx,
            title="Select the semester of the new co-op server",
            options=[("Fall", "Fall"), ("Spring", "Spring"), ("Summer", "Summer")],
        )
        if not semester:
            return
        start_date = await text_menu(
            ctx,
            title="Start Date",
            description="Please provide the start date of this co-op term in the form MM/DD/YY (e.g. 05/17/2021)",
            re_string=r"[0-9]{2}\/[0-9]{2}\/[0-9]{4}",
        )
        if not start_date:
            return
        end_date = await text_menu(
            ctx,
            title="End Date",
            description="Please provide the end date of this co-op term in the form MM/DD/YY (e.g. 08/06/2021)",
            re_string=r"[0-9]{2}\/[0-9]{2}\/[0-9]{4}",
        )
        if not end_date:
            return
        # Create Guild
        with open(ICON_PATH, "rb") as icon:
            icon = icon.read()
        new_guild = await ctx.bot.create_guild(f"{year} {semester} Co-op Term", icon=icon)
        if config["guilds"].get(str(new_guild.id)) is None:
            config["guilds"][str(new_guild.id)] = {}
        # Emojis
        for emoji in EMOJIS_PATH.iterdir():
            with open(emoji, "rb") as emoji_img:
                emoji_img = emoji_img.read()
            await new_guild.create_custom_emoji(name=emoji.stem, image=emoji_img)
        # Roles
        await new_guild.default_role.edit(
            permissions=discord.Permissions(change_nickname=False),
        )
        admin_role = await new_guild.create_role(
            name="Admin",
            mentionable=True,
            colour=Colour.from_rgb(*ADTRAN_BLURPLE),
            permissions=discord.Permissions(administrator=True),
        )
        fourth_role = await new_guild.create_role(
            name="4th Termer",
            mentionable=True,
            hoist=True,
            colour=Colour.gold(),
            permissions=discord.Permissions(
                read_messages=True,
                send_messages=True,
                create_instant_invite=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True,
                mention_everyone=True,
                read_message_history=True,
                use_slash_commands=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
            ),
        )
        third_role = await new_guild.create_role(
            name="3rd Termer",
            mentionable=True,
            hoist=True,
            colour=Colour.purple(),
            permissions=discord.Permissions(
                read_messages=True,
                send_messages=True,
                create_instant_invite=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True,
                mention_everyone=True,
                read_message_history=True,
                use_slash_commands=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
            ),
        )
        await new_guild.create_role(
            name="2nd Termer",
            mentionable=True,
            hoist=True,
            colour=Colour.blue(),
            permissions=discord.Permissions(
                read_messages=True,
                send_messages=True,
                create_instant_invite=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True,
                mention_everyone=True,
                read_message_history=True,
                use_slash_commands=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
            ),
        )
        await new_guild.create_role(
            name="1st Termer",
            mentionable=True,
            hoist=True,
            colour=Colour.green(),
            permissions=discord.Permissions(
                read_messages=True,
                send_messages=True,
                create_instant_invite=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True,
                mention_everyone=True,
                read_message_history=True,
                use_slash_commands=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
            ),
        )
        mod_role = await new_guild.create_role(
            name="Mod",
            mentionable=True,
            colour=Colour.from_rgb(*ADTRAN_BLURPLE),
            permissions=discord.Permissions(manage_messages=True),
        )
        register_role = await new_guild.create_role(
            name="REGISTER",
            permissions=discord.Permissions(read_messages=True, read_message_history=True, view_channel=False),
        )
        for college, colors in config["colleges"].items():
            await new_guild.create_role(name=college, mentionable=True, colour=Colour.from_rgb(*colors))
        # Channels
        categories = await new_guild.fetch_channels()
        teatime_channel = await new_guild.create_text_channel("tea-table", position=1, category=categories[0])
        games_channel = await new_guild.create_text_channel("games", position=2, category=categories[0])
        overwrites = {
            new_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            third_role: discord.PermissionOverwrite(read_messages=True),
        }
        await new_guild.create_text_channel(
            "third-term-mafia", overwrites=overwrites, position=3, category=categories[0]
        )
        overwrites = {
            new_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            fourth_role: discord.PermissionOverwrite(read_messages=True),
        }
        await new_guild.create_text_channel(
            "fourth-term-bar", overwrites=overwrites, position=4, category=categories[0]
        )
        info_category = await new_guild.create_category("info", position=0)
        overwrites = {new_guild.default_role: discord.PermissionOverwrite(send_messages=False)}
        welcome_channel = await info_category.create_text_channel("welcome", overwrites=overwrites, position=0)
        important_channel = await info_category.create_text_channel("important", position=1)
        bot_channel = await info_category.create_text_channel("bot-hell", position=2)
        overwrites = {
            new_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            mod_role: discord.PermissionOverwrite(read_messages=True),
        }
        mod_bot_channel = await info_category.create_text_channel("mod-commands", overwrites=overwrites, position=3)
        overwrites = {
            new_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            register_role: discord.PermissionOverwrite(read_messages=True),
        }
        register_channel = await info_category.create_text_channel("register-now", overwrites=overwrites, position=4)
        await new_guild.create_voice_channel("Tea Time", position=1, category=categories[1])
        await new_guild.create_voice_channel("Adtran Tears", position=2, category=categories[1])
        await categories[0].edit(position=0)
        await info_category.edit(position=1)
        await categories[1].edit(position=2)
        # Configuration Update
        config["guilds"][str(new_guild.id)]["time"] = {}
        config["guilds"][str(new_guild.id)]["time"]["start"] = start_date
        config["guilds"][str(new_guild.id)]["time"]["end"] = end_date
        config["guilds"][str(new_guild.id)]["admin"] = admin_role.id
        config["guilds"][str(new_guild.id)]["mod"] = mod_role.id
        config["guilds"][str(new_guild.id)]["bot"] = bot_channel.id
        config["guilds"][str(new_guild.id)]["important"] = important_channel.id
        config["guilds"][str(new_guild.id)]["teatime"] = teatime_channel.id
        config["guilds"][str(new_guild.id)]["games"] = games_channel.id
        config["guilds"][str(new_guild.id)]["mod-bot"] = mod_bot_channel.id
        config["guilds"][str(new_guild.id)]["register"] = register_role.id
        update_config()
        await new_guild.edit(system_channel=welcome_channel)
        # Send Notifications
        await send_msg(
            None,
            title="Register Now",
            description="You have been DM'd by the bot, please read the instructions and register in response to the DM",
            channel=register_channel,
        )
        await ctx.channel.send(await welcome_channel.create_invite())


class User(Cog, description="The base commands available to you"):
    def __init__(self, bot):
        self.bot = bot
        self.notify_teatime.start()
        self.notify_timecard.start()
        self.notify_end_of_term.start()

    @command(
        checks=[dm_only],
        brief="Register in the server",
        description="Register in the server with your term number, school, and team",
    )
    async def register(self, ctx):
        if config["members"].get(str(ctx.message.author.id)):
            coop_guild = await ctx.bot.fetch_guild(config["members"][str(ctx.message.author.id)])
            nickname = await text_menu(
                ctx,
                title="Enter your name",
                description="Please provide your name in the form First Last (e.g. Will Humphlett)",
                re_string=r"[a-zA-Z]+\s[a-zA-Z]+"
            )
            if nickname is None:
                return
            nickname = " ".join([word.capitalize() for word in nickname.split()])
            roles = []
            term_number = await reaction_menu(
                ctx,
                title="Select your term number",
                options=[
                    ("1st Term", [role for role in await coop_guild.fetch_roles() if role.name == "1st Termer"]),
                    ("2nd Term", [role for role in await coop_guild.fetch_roles() if role.name == "2nd Termer"]),
                    ("3rd Term", [role for role in await coop_guild.fetch_roles() if role.name == "3rd Termer"]),
                    ("4th Term", [role for role in await coop_guild.fetch_roles() if role.name == "4th Termer"]),
                ],
            )
            if term_number is None:
                return
            roles.append(term_number[0])
            school = await reaction_menu(
                ctx,
                title="Select your school",
                options=[(school, school) for school in config["colleges"].keys()] + [("Other", "Other")],
            )
            if school is None:
                return
            elif school == "Other":
                existing_schools = [role.name for role in await coop_guild.fetch_roles()]
                new_school = await text_menu(
                    ctx,
                    title="Enter the name of your school",
                    description="Please omit the 'University of' portion of your school name. (e.g. Auburn University becomes Auburn, UAH becomes Alabama Huntsville)",
                    re_string=r"[a-zA-Z\s]+",
                )
                if new_school is None:
                    return
                new_school = new_school.capitalize()
                if new_school == "Other" or new_school in existing_schools:
                    await send_msg(
                        ctx,
                        title="Haha, very funny",
                        description="Restart your registration punk ass edge testing bitch",
                    )
                    return
                school_colors = await text_menu(
                    ctx,
                    title="Enter the color of your school",
                    description="Please provide the rgb color code of your school's main color in the form (###,###,###) with no leading zeros",
                    re_string=r"\([0-9]{1,3},[0-9]{1,3},[0-9]{1,3}\)"
                )
                if school_colors is None:
                    return
                school_colors = school_colors.strip().replace("(", "").replace(")", "").split(",")
                school_colors = tuple(int(color) for color in school_colors)
                config["colleges"][new_school] = list(school_colors)
                update_config()
                school = await coop_guild.create_role(name=new_school, colour=Colour.from_rgb(*school_colors), mentionable=True)
            else:
                school = [school_role for school_role in await coop_guild.fetch_roles() if school_role.name == school][0]
            roles.append(school)
            team_name = await text_menu(
                ctx,
                title="Please enter the name of your team",
                description="Please omit the 'Team' portion of your name. (e.g. Team HISS becomes HISS)",
                re_string=r"[a-zA-Z\s]+",
            )
            if team_name is None:
                return
            roles.append(await coop_guild.create_role(name=team_name, mentionable=True))
            member = await coop_guild.fetch_member(ctx.message.author.id)
            await member.edit(nick=nickname)
            await member.add_roles(*roles)
            register_role = coop_guild.get_role(config["guilds"][str(coop_guild.id)]["register"])
            await member.remove_roles(register_role)
            await send_msg(
                ctx,
                title="Successfully Registered",
                description=f"You have successfully registered in the {coop_guild.name} discord server, please enjoy!"
            )
            config["members"].pop(str(ctx.message.author.id))
            update_config()
        else:
            await send_msg(
                ctx,
                title="Register Error",
                description="You are not elegible to register for a server at this time. If you feel this is an error, please contact your server mod.",
            )

    @command(
        checks=[bot_only],
        brief="Change your nickname",
        description='Change your nickname to match the form First "Nick" Last',
    )
    async def nick(self, ctx, *nickname):
        nickname = " ".join(nickname)
        if '"' in ctx.author.nick:
            basename = ctx.author.nick.split('"')[0][:-1] + " " + ctx.author.nick.split('"')[-1][1:]
        else:
            basename = ctx.author.nick
        if nickname == "":
            await ctx.author.edit(nick=basename)
            await send_msg(ctx, title="Nickname Reset", description=f"Your name has been reset")
        elif ctx.author.nick is None:
            await send_msg(ctx, title="Nickname Error", description="Your nickname must first be set to First Last")
        elif '"' in nickname:
            await send_msg(ctx, title="Nickname Error", description="Your nickname cannot contain '\"'")
        else:
            if len(basename) + len(nickname) + 3 > 32:
                await send_msg(
                    ctx,
                    title="Nickname Error",
                    description=f"Your nickname cannot be longer than {32 - len(basename) - 3} characters",
                )
            else:
                nickname = basename.split()[0] + ' "' + nickname + '" ' + basename.split()[1]
                await ctx.author.edit(nick=nickname)
                await send_msg(ctx, title="Nickname Changed", description=f"You are now {nickname}")

    @command(
        checks=[bot_only],
        brief="Find the ghost op",
        description="Find the ghost op by number of messages sent",
    )
    async def ghost(self, ctx):
        wait_msg = await send_msg(
            ctx, title="Please Wait", description="Calculating the ghost op, please wait while this is done"
        )
        text_channels = []
        for channel in await ctx.guild.fetch_channels():
            if type(channel) == discord.TextChannel:
                text_channels.append(channel)
        ghost_ops = {}
        for channel in text_channels:
            async for msg in channel.history():
                if msg.author.bot:
                    continue
                elif ghost_ops.get(msg.author.name) is None:
                    ghost_ops[msg.author.name] = 1
                else:
                    ghost_ops[msg.author.name] += 1
        await wait_msg.delete()
        ghost_op = sorted([(k, v) for k, v in ghost_ops.items()], key=lambda x: x[1])[0]
        await send_msg(
            ctx,
            title="Ghost Op Found",
            description=f"The current ghost op is {ghost_op[0]} as they have only sent {ghost_op[1]} messages",
        )

    @command(
        brief="View the time until the next teatime", description="View the time until the next teatime is happening"
    )
    async def teatime(self, ctx):
        if config["guilds"][str(ctx.guild.id)].get("time") and datetime.now() < datetime.strptime(
            config["guilds"][str(ctx.guild.id)]["time"]["end"], "%m/%d/%Y"
        ):
            next_teatime = await next_scheduled(*SCHEDULED["teatime"])
            diff = next_teatime - datetime.now()
            days, hours, minutes, seconds = (
                diff.days,
                diff.seconds // 3600,
                (diff.seconds // 60) % 60,
                diff.seconds % 60,
            )
            await send_msg(
                ctx,
                title="Next Teatime",
                description=f"The next teatime is happening in {days} days, {hours} hours, {minutes} minutes, and {seconds} seconds.",
            )
        else:
            await send_msg(ctx, title="No Teatime", description="There are no more teatimes for you to join")

    @loop()
    async def notify_teatime(self):
        wait = await next_scheduled(*SCHEDULED["teatime"]) - datetime.now()
        await asyncio.sleep(wait.days * DAYS_TO_SECONDS + wait.seconds)
        for _, v in config["guilds"].items():
            if v.get("teatime") is None or v.get("time") is None:
                continue
            if (
                datetime.strptime(v["time"]["start"], "%m/%d/%Y")
                < datetime.now()
                < datetime.strptime(v["time"]["end"], "%m/%d/%Y")
            ):
                await send_msg(
                    None,
                    title="Teatime",
                    description="Its teatime, join up in the teatime voice channel",
                    channel=self.bot.get_channel(v["important"]),
                )

    @notify_teatime.before_loop
    async def before_notify_teatime(self):
        await self.bot.wait_until_ready()

    @command(brief="View the time until the next timecard", description="View the time until the next timecard is due")
    async def timecard(self, ctx):
        if config["guilds"][str(ctx.guild.id)].get("time") and datetime.now() < datetime.strptime(
            config["guilds"][str(ctx.guild.id)]["time"]["end"], "%m/%d/%Y"
        ):
            next_timecard = await next_scheduled(*SCHEDULED["timecard"])
            diff = next_timecard - datetime.now()
            days, hours, minutes, seconds = (
                diff.days,
                diff.seconds // 3600,
                (diff.seconds // 60) % 60,
                diff.seconds % 60,
            )
            await send_msg(
                ctx,
                title="Next Timecard",
                description=f"The next timecard is due in {days} days, {hours} hours, {minutes} minutes, and {seconds} seconds.",
            )
        else:
            await send_msg(ctx, title="No Timecard", description="There are no more timecards for you to turn in")

    @loop()
    async def notify_timecard(self):
        wait = await next_scheduled(*SCHEDULED["timecard"]) - datetime.now()
        await asyncio.sleep(wait.days * DAYS_TO_SECONDS + wait.seconds)
        for _, v in config["guilds"].items():
            if v.get("important") is None or v.get("time") is None:
                continue
            if (
                datetime.strptime(v["time"]["start"], "%m/%d/%Y")
                < datetime.now()
                < datetime.strptime(v["time"]["end"], "%m/%d/%Y")
            ):
                await send_msg(
                    None,
                    title="Timecard Notification",
                    description="Your timecards are due today",
                    channel=self.bot.get_channel(v["important"]),
                )

    @notify_timecard.before_loop
    async def before_notify_timecard(self):
        await self.bot.wait_until_ready()

    @loop()
    async def notify_end_of_term(self):
        end_of_terms = []
        for _, v in config["guilds"].items():
            if v.get("time") and datetime.now() < datetime.strptime(f"{v['time']['end']}:23", "%m/%d/%Y:%H"):
                end_of_terms.append(v)
        if len(end_of_terms) == 0:
            await asyncio.sleep(86400)
        else:
            next_end = sorted(end_of_terms, key=lambda x: datetime.strptime(x["time"]["end"], "%m/%d/%Y"))[0]
            await asyncio.sleep(
                int(
                    datetime.now().timestamp()
                    - datetime.strptime(next_end["time"]["end"], "%m/%d/%Y").timestamp()
                    - 10800
                )
            )
            announce = await self.bot.fetch_channel(next_end["important"])
            await send_msg(
                None,
                title="Congratulations!!!",
                description="Congrats on reaching the end of term!",
                channel=announce,
            )

    @notify_end_of_term.before_loop
    async def before_notify_timecard(self):
        await self.bot.wait_until_ready()


class Utility(Cog, description="The utility commands available to you"):
    def __init__(self, bot):
        self.bot = bot

    @command(brief="View the about info", description="View the about info regarding the bot")
    async def about(self, ctx):
        app_info = await ctx.bot.application_info()
        await send_msg(
            ctx,
            title=f"About the ADTRAN Co-op Bot",
            description=[
                "This bot is meant to create and rule the co-op discord server",
                f"For issues or enhancements, please contact Will Humphlett",
            ],
            footer=f"Will Humphlett ({app_info.owner})",
        )

    @command(brief="Ping the bot", description="Ping the bot and view the current latency")
    async def ping(self, ctx):
        await send_msg(
            ctx,
            title=f"{ctx.bot.user.name} Bot Latency",
            description=f"pong! (bot latency is {round(ctx.bot.latency, 3)} s)",
        )


class CustomHelpCommand(DefaultHelpCommand):
    async def send_pages(self):
        destination = self.get_destination()
        embed = discord.Embed(
            color=discord.Color.from_rgb(*ADTRAN_BLURPLE),
            description="",
            title="Co-op Command Guide",
        )
        for page in self.paginator.pages:
            embed.description += page
        await destination.send(embed=embed)


def main():
    load_dotenv()
    bot = Bot(command_prefix="!", intents=Intents.all())
    bot.add_cog(Owner(bot))
    bot.add_cog(Admin(bot))
    bot.add_cog(User(bot))
    bot.add_cog(Utility(bot))
    bot.help_command = CustomHelpCommand(no_category="Help")
    bot.run(os.getenv("DISCORD_API_TOKEN"))
