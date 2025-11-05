# -*- coding: utf-8 -*-
# user/startup.py
"""Logger setter and CLI argument parsers."""

from argparse import (
    ArgumentParser,
    Namespace,
    RawTextHelpFormatter,
    ArgumentTypeError,
    _SubParsersAction,
)
import logging
from pathlib import Path
from textwrap import dedent
from typing import Callable

from clinictracker.config import TARGET_BASE_URL, TARGET_TZ, BROWSER_CHOICES
from clinictracker.user.models import UserDict, PERIOD_USER, MAX_ITEMS_USER
from clinictracker.user.config import CommandName, USERS_JSON_PATH, TABLE_NAMES
from clinictracker.startup import MyLogger, setup_logger
from clinictracker.startup import trim_str
from clinictracker.user.helpers import is_valid_email, user_dicts_to_str


# ---------------------------------------------------------------------|
# CLI arguments
USER_FORMAT = (
    "Format:\n    -u "
    '"username=str [nickname=str] emails=str[,...] cities=str[,...] '
    '[period=int] [nmax=int]"'
)
USER_ARGS_HINT = (
    f"{USER_FORMAT}\n"
    + dedent(
        """
    Fields:
        username: a unique string (case insensitive)
        nickname: default to null
        emails: recipients (if not given and username is a valid email,
                set it as a recipient)
        cities: town/city list
        period: schedule period in days (default to 1 or from $PERIOD_USER)
        nmax: maximum number of items to collect
              (default to 10 or from $MAX_ITEMS_USER)
    """
    ).strip()
)


def user_parser_closure(
    command_name: CommandName,
) -> Callable[[str], UserDict]:
    """Factory function that creates a parser for a specific command."""

    def parse_user_args(user_string: str) -> UserDict:
        """Parses a user in format: 'username=str emails=str,... ...'
        User fields will be validated when creating `User` objects.
        """
        parts = user_string.split()
        user_dict: UserDict = {}
        for part in parts:
            if '=' not in part:
                raise ArgumentTypeError(f"Invalid arg: {part}\n" + USER_FORMAT)

            key, value = [trim_str(s) for s in part.split('=', maxsplit=1)]
            match key:
                case 'username':
                    user_dict[key] = value.lower()
                case 'emails':
                    user_dict[key] = [
                        trim_str(s).lower() for s in value.split(',')
                    ]
                case 'cities':
                    user_dict[key] = [trim_str(s) for s in value.split(',')]
                case 'period' | 'nmax':
                    if value.split('-', 1)[-1].isdigit():
                        user_dict[key] = int(value)
                    else:
                        raise ArgumentTypeError(f"'{key}' must be a number.")
                case _:
                    raise ArgumentTypeError(
                        f"Unknown field: {key}\n" + USER_FORMAT
                    )

        # Fill in 'username'
        _username: str = trim_str(user_dict.get('username', ''))
        user_dict['username'] = _username

        # Set defaults (could be set later but set here for logging)
        if command_name == CommandName.ADD:
            # If no email specified and username is an email, use it
            if not user_dict.get('emails') and is_valid_email(_username):
                user_dict['emails'] = [_username]
            # Fill with defaults
            user_dict['period'] = user_dict.get('period', PERIOD_USER)
            user_dict['nmax'] = user_dict.get('nmax', MAX_ITEMS_USER)

        return user_dict

    return parse_user_args


def get_args_and_logger_for_service() -> (
    tuple[Namespace, logging.Logger | MyLogger]
):
    """Gets CLI arguments and sets the logger."""
    parser = ArgumentParser(
        description=(
            "Fetches clinic updates across a specified region "
            "from a target website and send to user."
        ),
        formatter_class=RawTextHelpFormatter,
    )
    # Query args
    parser.add_argument(
        '--url',
        type=str.lower,
        metavar='str',
        default=TARGET_BASE_URL,
        help="The target base URL (default from $TARGET_BASE_URL)",
    )
    parser.add_argument(
        '--tz',
        type=str,
        metavar='str',
        default=TARGET_TZ,
        help=(
            "TZ identifier (IANA Time Zones) of the target website\n"
            "(use local time zone if empty) (default from $TARGET_TZ)"
        ),
    )
    # Database operations
    subparsers: _SubParsersAction[ArgumentParser] = parser.add_subparsers(
        dest='command',
        metavar='COMMAND',
        help=(
            "Operations to manage user data in the database "
            "(no data fetching and sending)\n"
            f"Valid commands: {', '.join(name for name in CommandName)}"
        ),
    )
    # Subcommand: list
    list_parser: ArgumentParser = subparsers.add_parser(
        CommandName.LIST, description="List all users"
    )
    list_parser.add_argument(
        '-u',
        '--usernames',
        nargs='+',
        type=str.lower,
        metavar='str',
        help="Usernames (if not provided, list all users)",
    )
    # Subcommand: add
    add_parser: ArgumentParser = subparsers.add_parser(
        CommandName.ADD,
        description="Insert users (overridden by --load)",
        formatter_class=RawTextHelpFormatter,
    )
    add_parser.add_argument(
        '-u',
        '--user',
        required=True,
        metavar='"FIELDS"',
        action='append',  # allows multiple --user flags
        type=user_parser_closure(CommandName.ADD),
        help=USER_ARGS_HINT,
    )
    # Subcommand: update
    update_parser: ArgumentParser = subparsers.add_parser(
        CommandName.UPD,
        description=(
            "Update users\n"
            "(overridden by --load; will prompt for confirmation)"
        ),
        formatter_class=RawTextHelpFormatter,
    )
    update_parser.add_argument(
        '-u',
        '--user',
        required=True,
        metavar='"FIELDS"',
        action='append',  # allows multiple --user flags
        type=user_parser_closure(CommandName.UPD),
        help=USER_ARGS_HINT,
    )
    # Subcommand: delete
    delete_parser: ArgumentParser = subparsers.add_parser(
        CommandName.DEL,
        description=(
            "Delete users\n"
            "(overridden by --load; will prompt for confirmation)"
        ),
    )
    delete_parser.add_argument(
        '-u',
        '--usernames',
        nargs='+',
        type=str.lower,
        required=True,
        metavar='str',
        help="List of usernames",
    )
    # Subcommand: reset
    subparsers.add_parser(
        CommandName.RESET,
        description=(
            "**CAUTION** Reset user id sequence in database. Perform "
            "after updating from file\n(will prompt for confirmation) "
            "(default: false)"
        ),
        formatter_class=RawTextHelpFormatter,
    )
    # Subcommand: clear
    clear_parser: ArgumentParser = subparsers.add_parser(
        CommandName.CLEAR,
        description=(
            "**CAUTION** Empty tables and reset user id sequence\n"
            "(overridden by --load; will prompt for confirmation) "
            "(default: false)"
        ),
        formatter_class=RawTextHelpFormatter,
    )
    clear_parser.add_argument(
        '-t',
        '--tables',
        nargs='+',
        type=str.lower,
        metavar='str',
        choices=TABLE_NAMES,
        help="Table names: %(choices)s (if not provided, clear all tables)",
    )
    # Table args
    parser.add_argument(
        '--skip-creation',
        action='store_true',
        help="Skip creating tables (default: false)",
    )
    parser.add_argument(
        '--create-only',
        action='store_true',
        help=(
            "Exit after creating tables without any further operation "
            "(default: false)"
        ),
    )
    # User data args
    parser.add_argument(
        '-f',
        '--file',
        type=Path,
        metavar='str',
        default=USERS_JSON_PATH,
        help=(
            "JSON file containing user data "
            "(default to 'data/users.json' or from $USERS_JSON_PATH)"
        ),
    )
    parser.add_argument(
        '--load',
        action='store_true',
        help=(
            "Load user data from the JSON file specified by -f "
            "and update the data in database\n(overriding "
            "add/update/delete/clear commands) (default: false)"
        ),
    )
    parser.add_argument(
        '--del',
        dest='delete',
        action='store_true',
        help=(
            "**CAUTION** When --load is selected and the JSON file specified "
            "by -f is non-empty,\ndelete users that are not in the file "
            "(will prompt for confirmation) (default: false)"
        ),
    )
    parser.add_argument(
        '--save',
        action='store_true',
        help=(
            "Save all user data to the JSON file specified by -f after "
            "other operations,\nbacking up existing files (default: false)"
        ),
    )
    # Other database args
    parser.add_argument(
        '--crud-only',
        action='store_true',
        help=(
            "Exit after managing user data without any further operation\n"
            "(no effect if COMMAND is specified) (default: false)"
        ),
    )
    # Other service args
    parser.add_argument(
        '--send',
        action='store_true',
        help=(
            "Send fetched data to users based on their settings\n"
            "(default: print content to STDOUT without sending)"
        ),
    )
    parser.add_argument(
        '--ignore-hash',
        action='store_true',
        help=("Don't filter out items that are already sent (default: false)"),
    )
    parser.add_argument(
        '-u',
        '--usernames',
        nargs='+',
        type=str.lower,
        metavar='str',
        help="List of usernames. If specified, only send to these users",
    )
    parser.add_argument(
        '--retries',
        type=int,
        metavar='int',
        default=0,
        help=(
            "Maximum retries if timeout, excluding the initial attempt "
            "(default: 0)"
        ),
    )
    # Browser args
    parser.add_argument(
        '-H',
        '--headed',
        action='store_true',
        help="Run in headed mode (default: headless)",
    )
    parser.add_argument(
        '-b',
        '--browser',
        metavar='str',
        choices=BROWSER_CHOICES,
        default='chromium',
        help="Select a browser from: %(choices)s (default: %(default)s)",
    )
    parser.add_argument(
        '--headless-shell',
        dest='shell',
        action='store_true',
        help=(
            "Use a separate headless shell for chromium headless mode\n"
            "(https://playwright.dev/python/docs/browsers#chromium-headless-shell)"
        ),
    )
    # Debugging args
    parser.add_argument(
        '--debug',
        action='store_true',
        help=(
            "Set the logging level to DEBUG "
            "(default to false or from $DEBUG_MODE)"
        ),
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help=(
            "Exit after database connection without any further operation "
            "(default: false)"
        ),
    )
    parser.add_argument(
        '-q',
        '--quiet',
        action='store_true',
        help=(
            "Suppress INFO level outputs unless --debug is selected "
            "(default: print all)"
        ),
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help=(
            "Dry run for data management and exit before data fetching "
            "(default: false)"
        ),
    )

    args = parser.parse_args()
    validate_args_for_service(args)

    logger = setup_logger(
        name='' if args.debug else __name__,
        is_quiet=args.quiet if not args.debug else False,
    )

    logger.debug(f"Args:\n{vars(args)}")

    match args.command:
        case CommandName.LIST:
            logger.debug(
                "Users to look up: "
                f"{', '.join(args.usernames) if args.usernames else 'all'}"
            )
        case CommandName.ADD | CommandName.UPD:
            logger.debug(
                f"Users to {args.command}:\n" + user_dicts_to_str(args.user)
            )
        case CommandName.DEL:
            logger.debug(f"Users to delete: {', '.join(set(args.usernames))}")
        case CommandName.CLEAR:
            logger.debug(
                "Tables to clear: "
                + ', '.join(set(args.tables) if args.tables else TABLE_NAMES)
            )

    return args, logger


def validate_args_for_service(args: Namespace) -> None:
    """Validates CLI arguments.
    User fields will be validated when creating `User` objects.
    """
    if not trim_str(args.url):
        raise ValueError("Missing URL. See --help")

    if (args.load or args.save) and not args.file:
        raise ValueError("A file path must be specified by -f/--file.")

    if args.retries < 0:
        raise ValueError("Value of --retries must be non-negative.")
