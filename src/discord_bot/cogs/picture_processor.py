import os.path
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks

from discord_bot.log_setup import logger
from discord_bot.utils import utils as ut


### @package misc
#
# Collection of miscellaneous helpers.
#


class PictureProcessor(commands.Cog):
    """
    Various useful Commands for everyone
    """

    def __init__(self, bot, datat_path="data/"):
        self.bot: commands.Bot = bot
        self.storage: dict[discord.member, set[discord.Message]] = {}
        self.data_path = datat_path
        self.dm_walk_task = self.walk_dms.start()

    # Example for an event listener
    # This one will be called on each message the bot receives
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        print(message.content)
        print(message.channel)
        print("...")
        print(self.bot.private_channels)
        print(self.bot.get_all_channels())

    @tasks.loop(seconds=4)
    async def walk_dms(self):
        chat: discord.DMChannel
        channels = self.bot.private_channels
        logger.info(f"Walking {len(channels)} channels")
        channels = [await self.bot.fetch_channel(1158875005745115186)]
        for chat in channels:
            logger.info(f"Checking chat with {chat.recipient.name}")
            dir_path = f"{self.data_path}/{chat.id}"
            if not os.path.isdir(dir_path):
                os.mkdir(dir_path)

            async for message in chat.history(limit=None):

                print(message)
                if message.author == chat.me:
                    continue

                for attachment in message.attachments:
                    if attachment.content_type != "image":
                        continue

                    file_name = f"{dir_path}/{message.id}_{attachment.id}.png"
                    if os.path.isfile(file_name):
                        continue

                    await attachment.to_file(filename=file_name)
                    logger.info(f"Found new file - saving in '{file_name}'")


    # make sure we're online before starting
    @walk_dms.before_loop
    async def before_walk(self):
        logger.info(f"Waiting for scan of DMs to begin")
        await self.bot.wait_until_ready()

    # we only want the task to run once
    # @walk_dms.after_loop
    # async def after_walk(self):
    #     self.walk_dms.stop()



async def setup(bot):
    await bot.add_cog(PictureProcessor(bot))
