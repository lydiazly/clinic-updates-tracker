# -*- coding: utf-8 -*-
# user/config.py
"""Configuration and constants."""
from argparse import Namespace
from dataclasses import dataclass
from dotenv import load_dotenv
from enum import StrEnum  # python 3.11+
import os
from pathlib import Path
from typing import NamedTuple, Any

from clinictracker.config import Config
from clinictracker.user.models import User
from clinictracker.user.helpers import create_user_from_dict


load_dotenv()

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Minimum days to look back (before filtering by hash values)
DAYS_BACK_MIN: int = 2
# Minimum items to collect in full list (before filtering for each user)
MAX_ITEMS_MIN: int = 10
# Extra days to keep records beyond the maximum period among users
CLEANUP_BUFFER_DAYS: int = 7

# Source file containing a list of user data
USERS_JSON_PATH: Path = Path(os.getenv('USERS_JSON_PATH', './data/users.json'))


class CommandName(StrEnum):
    """User data operation commands: LIST, ADD, UPD, DEL, RESET, CLEAR"""

    LIST = 'list'
    ADD = 'add'
    UPD = 'update'
    DEL = 'delete'
    RESET = 'reset'
    CLEAR = 'clear'


class CommandRequest(NamedTuple):
    """A user data operation command and its payload.

    Attributes:
        name (CommandName): The command that needs to be executed with data
        data (list[User] | list[dict] | list[str] | None): The payload
    """

    name: CommandName
    data: list[User] | list[dict[str, Any]] | list[str] | None


@dataclass(frozen=True)
class ServiceConfig(Config):
    """User service configuration.

    Attributes:
        debug (bool): Set the logging level to DEBUG
        test (bool): Exit after database connection
        headed_mode (bool): Headed mode
        browser_name (str): Browser name
        headless_shell (bool): Use a separate chromium headless shell
        url (str): The target base URL
        tz (str): TZ identifier (IANA Time Zones) of the target website
        command (CommandRequest | None): (name, data)
        skip_creation (bool): Skip creating tables
        creation_only (bool): Exit after creating tables
        json_path (Path): JSON file containing user data
        load_users (bool): Update user data from the JSON file
        delete_users (bool): If load_users, delete users that are not in
                             the JSON file
        save_users (bool): Save/Overwrite all user data to the JSON file
        upsert_only (bool): Exit after updating users
        send (bool): Send fetched data to users
    """

    url: str
    tz: str
    command: CommandRequest | None
    skip_creation: bool
    creation_only: bool
    json_path: Path
    load_users: bool
    delete_users: bool
    save_users: bool
    upsert_only: bool
    send: bool


def load_config_for_service(args: Namespace) -> ServiceConfig:
    """Loads configuration from args and environment for user service."""
    command_request: CommandRequest | None = None
    if args.command is not None:
        command_name = CommandName(args.command)
        match command_name:
            case CommandName.ADD:
                command_request = CommandRequest(
                    name=command_name,
                    data=list(map(create_user_from_dict, args.user)),
                )
            case CommandName.UPD:
                command_request = CommandRequest(
                    name=command_name,
                    data=args.user,
                )
            case CommandName.LIST | CommandName.DEL:
                command_request = CommandRequest(
                    name=command_name,
                    data=args.usernames,
                )
    return ServiceConfig(
        debug=args.debug or DEBUG_MODE,
        test=args.test,
        headed_mode=args.headed,
        browser_name=args.browser,
        headless_shell=args.shell,
        url=args.url,
        tz=args.tz,
        command=command_request,
        skip_creation=args.skip_creation,
        creation_only=args.creation_only,
        json_path=args.file,
        load_users=args.load,
        delete_users=args.delete if args.load and args.file else False,
        save_users=args.save,
        upsert_only=args.upsert_only,
        send=args.send,
    )
