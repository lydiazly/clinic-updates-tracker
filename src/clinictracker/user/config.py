# -*- coding: utf-8 -*-
# user/config.py
"""Configuration and constants."""

from argparse import Namespace
from dataclasses import dataclass
from dotenv import load_dotenv
from enum import StrEnum, auto  # python 3.11+
import os
from pathlib import Path
from typing import NamedTuple

from clinictracker.config import Config, APP_ENV
from clinictracker.startup import trim_str
from clinictracker.user.models import User, UserDict
from clinictracker.user.helpers import (
    create_user_from_dict,
    get_valid_user_dict,
)


load_dotenv()

DEBUG_MODE: bool = os.getenv('DEBUG_MODE', 'false').strip().lower() == 'true'
SEND_EMAILS: bool = os.getenv('SEND_EMAILS', 'false').strip().lower() == 'true'

PGSERVICEFILE: str = os.getenv('PGSERVICEFILE', '').strip()
PGSERVICE_PATH: Path = (
    Path(PGSERVICEFILE).expanduser()
    if PGSERVICEFILE
    else (Path.home() / 'pg_service.conf')
)

PGPASSFILE: str = os.getenv('PGPASSFILE', '').strip()
PGPASS_PATH: Path = (
    Path(PGPASSFILE).expanduser() if PGPASSFILE else (Path.home() / '.pgpass')
)

PGSERVICE: str = os.getenv('PGSERVICE', APP_ENV).strip() or 'dev-local'

SECRETS_PATH: Path = Path(os.getenv('SECRETS_PATH', '.secrets').strip())

# Minimum days to look back (before filtering by hash values)
DAYS_BACK_MIN: int = int(os.getenv('DAYS_BACK_MIN', 2))  # default: 2 days
# Minimum items to collect in full list (before filtering for each user)
MAX_ITEMS_MIN: int = int(os.getenv('MAX_ITEMS_MIN', 10))  # default: 10 items
# Extra days to keep records beyond the maximum period among users
CLEANUP_BUFFER_DAYS: int = int(os.getenv('CLEANUP_BUFFER_DAYS', 7))

# Source file containing a list of user data
USERS_JSON_PATH: Path = Path(
    os.getenv('USERS_JSON_PATH', 'data/users.json').strip()
)


class ServiceName(StrEnum):
    DEV = auto()
    DEV_LOCAL = 'dev-local'
    PROD = auto()


class TableName(StrEnum):
    SENT = 'sent_items'
    USERS = auto()


# Tables in database
TABLE_NAMES: list[str] = [name for name in TableName]


class CommandName(StrEnum):
    """User data operation commands: LIST, ADD, UPD, DEL, RESET, CLEAR"""

    LIST = auto()
    ADD = auto()
    UPD = 'update'
    DEL = 'delete'
    RESET = auto()
    CLEAR = auto()


CommandDataType = (
    list[User] | list[UserDict] | list[str] | list[TableName] | None
)


class CommandRequest(NamedTuple):
    """A user data operation command and its payload.

    Attributes:
        name (CommandName): The command that needs to be executed with data
        data (CommandDataType): The payload
    """

    name: CommandName
    data: CommandDataType


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
        create_only (bool): Exit after creating tables
        json_path (Path): JSON file containing user data
        load_users (bool): Update user data from the JSON file
        delete_users (bool): If load_users, delete users that are not in
            the JSON file
        save_users (bool): Save/Overwrite all user data to the JSON file
        crud_only (bool): Exit after CRUD operations on users
        send (bool): Send fetched data to users
        forget_last (bool): Skip checking last sent time and items
        usernames (list[str]): Only send to these users
        retries (int): Maximum retries if timeout
        dryrun (bool): Dry run for data management then exit
    """

    url: str
    tz: str
    command: CommandRequest | None
    skip_creation: bool
    create_only: bool
    json_path: Path
    load_users: bool
    delete_users: bool
    save_users: bool
    crud_only: bool
    send: bool
    forget_last: bool
    usernames: list[str] | None
    retries: int
    dryrun: bool


def load_config_for_service(args: Namespace) -> ServiceConfig:
    """Loads configuration from args and environment for user service."""
    command_request: CommandRequest | None = None
    _usernames: list[str] | None = None
    _tables: list[TableName] = [name for name in TableName]
    if args.usernames is not None:
        _usernames = list(
            dict.fromkeys([trim_str(u).lower() for u in args.usernames])
        )  # no duplicates
    if hasattr(args, 'tables') and args.tables is not None:
        _tables = list(
            dict.fromkeys(
                [TableName(trim_str(t).lower()) for t in args.tables]
            )
        )  # no duplicates

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
                    data=list(map(get_valid_user_dict, args.user)),
                )
            case CommandName.LIST | CommandName.DEL:
                command_request = CommandRequest(
                    name=command_name,
                    data=_usernames,  # list[str] | None
                )
            case CommandName.CLEAR:
                command_request = CommandRequest(
                    name=command_name,
                    data=_tables,  # list[TableName]
                )
            case _:
                command_request = CommandRequest(name=command_name, data=None)

    return ServiceConfig(
        debug=args.debug or DEBUG_MODE,
        test=args.test,
        headed_mode=args.headed,
        browser_name=args.browser,
        headless_shell=args.shell,
        url=trim_str(args.url),
        tz=trim_str(args.tz),
        command=command_request,
        skip_creation=args.skip_creation,
        create_only=args.create_only,
        json_path=args.file,
        load_users=args.load,
        delete_users=args.load and args.file and args.delete,
        save_users=not args.dry_run and args.save,
        crud_only=args.crud_only,
        send=(
            not args.dry_run
            and args.command is None
            and (args.send or SEND_EMAILS)
        ),
        forget_last=args.command is None and args.forget_last,
        usernames=_usernames,
        retries=args.retries,
        dryrun=args.dry_run,
    )
