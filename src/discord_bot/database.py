import glob
import json
import os
from dataclasses import dataclass, field
from typing import Iterable, Callable, Any

import discord
from discord.ext import commands

from discord_bot.log_setup import logger

message_idT = int

@dataclass
class TeamRecord:
    team_name: str
    founder: discord.Member
    data_folder: str
    other_members: set[discord.Member]
    read_message_ids: set[message_idT] = field(default_factory=set, repr=False, compare=False)
    dm_channel: discord.DMChannel = None  # used to walk channels if we didn't get messages
    old_member_ids: set[int] = field(default_factory=set, repr=False, compare=False)

    def __post_init__(self):
        os.makedirs(self.data_folder)

    @property
    def full_team(self) -> set[discord.Member]:
        return self.other_members.union({self.founder,})

    # technically this data is not immutable...
    def __hash__(self):
        return self.team_name

    @staticmethod
    def to_id_list(s: Iterable):
        return [elm.id for elm in s]

    @staticmethod
    def to_obj_set(l: list[int], getter_fn: Callable[[int,], Any]):
        return {getter_fn(elm) for elm in l}

    def to_json(self):
        return {
            "team_name": self.team_name,
            "founder": self.founder.id,
            "other_members": self.to_id_list(self.other_members),
            "read_message_ids": list(self.read_message_ids),
            "dm_channel": self.dm_channel.id,
            "old_members": self.to_id_list(self.old_member_ids),
            "guild": self.founder.guild.id,  # needed to deserialize,
            "data_folder": self.data_folder
        }

    def write_to(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_json(), f)

    def write_to_disk(self, file_name="team_record.json"):
        self.write_to(f"{self.data_folder}/{file_name}")

    @staticmethod
    def from_json(file: str, bot: commands.Bot):
        with open(file, "r") as f:
            data = json.load(f)

        guild = bot.get_guild(data["guild"])
        # TODO why doesnt this seem to give a DMChannel?
        dm_channel: discord.DMChannel = bot.get_channel(data["dm_channel"])

        return TeamRecord(
            team_name=data["team_name"],
            data_folder=data["data_folder"],
            founder=guild.get_member(data["founder"]),
            other_members=TeamRecord.to_obj_set(data["other_members"], guild.get_member),
            read_message_ids=set(data["read_message_ids"]),
            dm_channel=dm_channel,
            old_member_ids=set(data["old_members"]),
        )


# okay. now why that?
# couldn't this simply be a member variable of PictureProcessor?
# no. because the module will be reloaded on fixes, so that the main bot and its data stays alive
# this is why we need to get the data out of the module
# the singleton ensures that the "instanced" DB will always be the same
# again: I'm so sorry.
# consider this my contribution to making LLMs a bit shittier when it comes to learning from open projects.
class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        else:
            logger.debug(f"The object '{cls.__name__}' was already initialized, returning inited object")
        return cls._instances[cls]

class SingletonDatabase(metaclass=Singleton):

    def __init__(self, bot: commands.Bot, restore_from_files: bool = True):
        # team name to members
        self.bot = bot
        self.teams: dict[discord.Member, TeamRecord] = dict()
        self.all_registered_members: set[discord.Member] = set()
        self.all_registered_team_names: set[str] = set()

        if restore_from_files:
            self.load_records_from_files()

    def load_records_from_files(self, file_names="team_record.json"):
        for file_path in glob.glob(f"data/**/{file_names}", recursive=True):
            team_record = TeamRecord.from_json(file_path, self.bot)

            self.teams[team_record.founder] = team_record
            self.all_registered_members.update(team_record.full_team)
            self.all_registered_team_names.add(team_record.team_name)

    def locate_member(self, m: discord.Member):
        if m not in self.all_registered_members:
            return None

        for tr in self.teams.values():
            if m in tr.full_team:
                return tr

        return None

    def validate_team_record(self, team_record: TeamRecord):
        if team_record.founder in self.all_registered_members:
            team = self.locate_member(team_record.founder)
            raise ValueError(f"You are already part of team '{team.team_name}', you can't create a new one.")

        for member in team_record.other_members:
            if member in self.all_registered_members:
                team = self.locate_member(team_record.founder)
                raise ValueError(
                    f"Player {member.mention} is already part of team '{team.team_name}' by '{team.founder.name}'. "
                    f"Team will not be created"
                )

        if team_record.team_name in self.all_registered_team_names:
            raise ValueError(f"Team with name '{team_record.team_name}' already exists. No team will be created.")

    def add_record(self, team_record: TeamRecord, validate=False):
        if validate:
            self.validate_team_record(team_record)

        # TODO: create folder here and write team to file

        # okay, we can write the data
        self.all_registered_members.update(team_record.full_team)
        self.all_registered_team_names.add(team_record.team_name)
        self.teams[team_record.founder] = team_record
        logger.info(
            f"Team '{team_record.team_name}' created by '{team_record.founder.id}'. "
            f"Other members: {len(team_record.other_members)}. Channel: {team_record.dm_channel.id}.")

        team_record.write_to_disk()

    def delete_team(self, key: TeamRecord | discord.Member):
        if type(key) is TeamRecord:
            key = key.founder

        # get record for right cleanup
        team_record = self.teams[key]

        # free members and name
        self.all_registered_members = self.all_registered_members - team_record.full_team
        self.all_registered_team_names = self.all_registered_team_names - {team_record.team_name,}

        # delete the key
        del self.teams[key]
        # we don't do file cleanup here.

        logger.info(f"Team '{team_record.team_name}' was deleted. Channel ID was: {team_record.dm_channel.id}")
        # TODO: update file

    def remove_member(self, member: discord.Member, team_record=None):
        if team_record is None:
            team_record = self.locate_member(member)

        # it's the founder and the team has other members
        if member == team_record.founder and len(team_record.other_members) > 0:
            raise ValueError(f"Founder can't remove the founder as long as other members are in it")

        # still the founder, but team is empty beside him
        elif member == team_record.founder:
            logger.warning(
                f"The team '{team_record.team_name}' is now empty, with 'None' as founder. Consider deleting it. "
                f"Keeping a headless team might cause unexpected side-effects!")
            team_record.founder = None

        # normal member
        else:
            team_record.other_members.remove(member)


        logger.info(f"Member {member.id} left team '{team_record.team_name}'")

        team_record.old_member_ids.add(member.id)
        self.all_registered_members.remove(member)
        # TODO: update file

    def save_or_update_records(self, file_name="team_record.json"):
        for record in self.teams.values():
            record.write_to_disk(file_name)
