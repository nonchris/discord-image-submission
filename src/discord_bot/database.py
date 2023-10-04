from dataclasses import dataclass, field

import discord

from discord_bot.log_setup import logger


@dataclass
class TeamRecord:
    team_name: str
    founder: discord.Member
    other_members: set[discord.Member]
    read_messages: set[discord.Message] = field(default_factory=set, repr=False, compare=False)
    dm_channel: discord.DMChannel = None

    @property
    def full_team(self) -> set[discord.Member]:
        return self.other_members.union({self.founder,})

    # technically this data is not immutable...
    def __hash__(self):
        return self.team_name


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
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SingletonDatabase, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # team name to members
        self.teams: dict[discord.Member, TeamRecord] = dict()
        self.all_registered_members: set[discord.Member] = set()
        self.all_registered_team_names: set[str] = set()


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

        # okay, we can write the data
        self.all_registered_members.update(team_record.full_team)
        self.all_registered_team_names.add(team_record.team_name)
        self.teams[team_record.founder] = team_record
        logger.info(
            f"Team '{team_record.team_name}' created by '{team_record.founder.id}'. "
            f"Other members: {len(team_record.other_members)}. Channel: {team_record.dm_channel.id}.")

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

        self.all_registered_members.remove(member)
