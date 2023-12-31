import asyncio
import atexit
import os.path
from typing import Literal, Optional

import discord
from discord import app_commands, Forbidden
from discord.ext import commands
from discord.ext import tasks

from discord_bot.environment import BASE_GUILD
from discord_bot.log_setup import logger
from discord_bot.utils import utils as ut
from discord_bot.database import SingletonDatabase, TeamRecord


### @package misc
#
# Collection of miscellaneous helpers.
#

register_command_name = "register"
unregister_command = "leave"

class PictureProcessor(commands.Cog):
    """
    Various useful Commands for everyone
    """

    def __init__(self, bot, datat_path="data/"):
        self.bot: commands.Bot = bot
        self.storage: dict[discord.member, set[discord.Message]] = {}
        self.data_path = datat_path
        self.database = SingletonDatabase(self.bot)
        # TODO: race condition when team isn't loaded but a team is created in that time (actually not a irl problem)
        #  solution: check if path exists and then load that team and raise error based on it
        if not self.database.teams:
            asyncio.create_task(self.database.load_records_from_files())

        self.dm_walk_task = self.walk_dms.start()
        self.save_records.start()
        atexit.register(self.shutdown_procedure)
        logger.info("Loaded.")


    @app_commands.command(name=register_command_name, description="Create a team")
    # @app_commands.guild_only
    async def register(
            self,
            interaction: discord.Interaction,
            team_name: str,
            # I am truly - TRULY sorry for everyone that has to read this...
            # but. hear me out.
            # Since discord doesn't allow for varargs I don't have another choice to allow for maximum options...
            # the limit of arguments is 25 - see:
            # https://discord.com/developers/docs/interactions/application-commands#application-command-object-application-command-option-structure
            # oh - before you ask - yes. these variables are used. pycharm just doesn't get it
            member1: discord.Member = None,
            member2: discord.Member = None,
            member3: discord.Member = None,
            member4: discord.Member = None,
            member5: discord.Member = None,
            member6: discord.Member = None,
            member7: discord.Member = None,
            member8: discord.Member = None,
            member9: discord.Member = None,
            member10: discord.Member = None,
            member11: discord.Member = None,
            member12: discord.Member = None,
            member13: discord.Member = None,
            member14: discord.Member = None,
            member15: discord.Member = None,
            member16: discord.Member = None,
            member17: discord.Member = None,
            member18: discord.Member = None,
            member19: discord.Member = None,
            member20: discord.Member = None,
            member21: discord.Member = None,
            member22: discord.Member = None,
            member23: discord.Member = None,
        ):
        """
        Command to register a team
        """
        def get_team_creation_error_embed(e: Exception):
            return ut.make_embed(
                name='Failed to create team',
                value=f"Reason: {e}, you can leave a team using `/{unregister_command}`. You're NOT able to join an existing team.",
                color=ut.red)

        # let me make up for the hell above by doing even more horrible things, but it's for the better. trust me.
        other_members_set = set()
        for member_i in range(1, 24):
            other_members_set.add(eval(f"member{member_i}"))

        # ensure that we don't have the bot and None there
        # TODO: maybe check that other users ain't other bots
        other_members_set = other_members_set - {None, self.bot.user}

        # check if all members are not registered in an other team and if the name is still available
        try:
            t = TeamRecord(team_name=team_name, founder=interaction.user, other_members=other_members_set)
            self.database.validate_team_record(t)
        except ValueError as e:
            await interaction.response.send_message(embed=get_team_creation_error_embed(e), ephemeral=True)
            return

        # try to contact the member via DM
        try:
            private_message = await interaction.user.send(
                embed=ut.make_embed(
                    name="You're all set - lets go!",
                    value="You're all set. Start submitting the pictures for your team here!\n"
                          "Please not that you are currently the ONLY person that can submit pictures for your team.",
                    color=ut.green
                )
            )
        except Forbidden as e:
            await interaction.response.send_message(
                embed=ut.make_embed(
                    name="Failed to create a DM with you",
                    value=f"Please check you privacy settings for that server.\n"
                          f"If you don't feel comfortable doing that consider the team creation by an other member.\n"
                          f"**No team** was created!",
                    color=ut.red
                ),
                ephemeral=True
            )
            return

        # set private channel to record
        t.dm_channel = private_message.channel
        t.data_folder = f"{self.data_path}/{private_message.channel.id}"

        # try to add it and validate the data again - maybe something changed in the meantime while doing a request
        # -> race-conditions
        try:
            self.database.add_record(t, validate=True)
        except ValueError as e:
            await interaction.response.send_message(embed=get_team_creation_error_embed(e), ephemeral=True)
            return

        # done!
        await interaction.response.send_message(
            embed=ut.make_embed(
                name='Your team is registered!',
                value=f'Go to your DMs and start submitting images for you team!')
        )

    @app_commands.command(name="which_team", description="Get the information in which team you're in.")
    async def which_team(self, interaction: discord.Interaction):
        team_record = self.database.locate_member(interaction.user)
        if team_record is None:
            await interaction.response.send_message(f"You're currently not part of a team.", ephemeral=True)
            return

        nl = "\n"
        await interaction.response.send_message(
            embed=ut.make_embed(
                title=f"You're part of team '{team_record.team_name}'",
                value=f"Created by {team_record.founder.mention}.\n"
                      f"Other members are:\n"
                      f"{nl.join(m.mention for m in team_record.other_members)}"
            ),
            ephemeral=True
        )

    @app_commands.command(name=unregister_command, description="Leave your team. You CAN'T JOIN an existing team!")
    async def leave(self, interaction: discord.Interaction):
        member = interaction.user
        team_record = self.database.locate_member(member)
        if team_record is None:
            await interaction.response.send_message("You're not part of a team you could leave.", ephemeral=True)
            return

        # founder can't leave as long as other members are part of it
        if team_record.founder == member and len(team_record.other_members) > 0:
            await interaction.response.send_message(
                embed=ut.make_embed(title="You can't leave!",
                                    value="The founder of a team can't leave as long as members are in it.\n"
                                          "If you want to leave, every member must leave beforehand.\n"
                                          "All progress will be lost when you leave.\n"
                                          "It is not possible to (re-)join an existing team!",
                                    color=ut.red),
                ephemeral=True

            )
            return

        # TODO "type yes validation"?

        # well, let the member leave

        # founder left - wipe it from the db
        if team_record.founder == member:
            self.database.delete_team(member)

        # we can just remove a normal member
        else:
            self.database.remove_member(member)

        await interaction.response.send_message(
            embed=ut.make_embed(
                title="You left.",
                value="You can now found a new team, joining an existing team is NOT possible.",
                color=ut.blue_light
            ),
            ephemeral=True
        )


    async def process_dm_message(self, m: discord.Message):

        # ignore own messages
        if m.author == self.bot.user:
            return

        # ignore message with zero attachments
        if len(m.attachments) == 0:
            return

        # get channel from team record to pin it on the member
        team_record = self.database.locate_member(m.author)

        logger.debug(f"Processing message from '{m.author.id}' with {len(m.attachments)} attachments.")

        was_picture_included = False

        # iterate attachments, save new images
        for attachment in m.attachments:
            if "image" not in attachment.content_type:
                continue

            # check if we know that file
            file_name = f"{team_record.data_folder}/{m.id}_{attachment.id}.png"
            if os.path.isfile(file_name):
                logger.debug(f"Already know file: {file_name}")
                continue

            # TODO: send the image to database, let it validate that we accept the image
            # save new file
            with open(file_name, "wb") as f:
                await attachment.save(f)
            logger.info(f"Found new file - saving in: {file_name}")
            was_picture_included = True

        # acknowledge file
        if was_picture_included:
            await m.add_reaction("\u2705")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        member = message.author
        logger.debug(message.content)

        if message.author == self.bot.user:
            return

        # we only do DMs here
        if type(message.channel) is not discord.DMChannel:
            return

        # member is not a team founder - let's see what we respond
        if member not in self.database.teams.keys():
            guild = self.bot.get_guild(BASE_GUILD)
            team = self.database.locate_member(member)
            await message.channel.send(
                f"You're in team '{team.team_name}', by {team.founder.name}. Only the creator can submit pictures."
                if team is not None else
                f"Please register your team on '{guild.name}' using `/{register_command_name}`."
            )
            return

        # member is a founder, process the message
        await self.process_dm_message(message)

    # TODO: use new DM storage system
    @tasks.loop(count=1)
    async def walk_dms(self):
        chat: discord.DMChannel

        team_records = self.database.teams.values()
        logger.info(f"Walking {len(team_records)} channels")
        for team_record in team_records:
            logger.info(f"Checking chat with {team_record.founder}")

            if team_record.dm_channel is None:
                logger.warning(f"No channel with '{team_record.founder.id}' found")
                continue

            async for message in team_record.dm_channel.history(limit=None):

                if message.created_at < team_record.creation_time:
                    logger.info(f"Breaking on: {message.id}, {message.created_at}")
                    break

                await self.process_dm_message(message)

        logger.info(f"All chats walked successful.")

    # make sure we're online before starting
    @walk_dms.before_loop
    async def before_walk(self):
        logger.info(f"Waiting for scan of DMs to begin")
        await self.bot.wait_until_ready()

    def __save_records(self):
        logger.info("Start saving of all data to disk...")
        self.database.save_or_update_records()
        logger.info("All data saved to disk")

    # we do it all 10 seconds, but we sleep additional time in the method
    # we don't need to write immediately after starting...
    @tasks.loop(seconds=10)
    async def save_records(self):
        await asyncio.sleep(110)
        self.__save_records()

    def shutdown_procedure(self):
        logger.warning(f"Shutdown was issued. saving data...")
        self.__save_records()

async def setup(bot):
    await bot.add_cog(PictureProcessor(bot))
