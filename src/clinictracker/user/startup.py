# -*- coding: utf-8 -*-
# user/startup.py
"""Logger setter and CLI argument parsers."""
from argparse import (
    ArgumentParser,
    Namespace,
    RawTextHelpFormatter,
    _SubParsersAction,
)
import logging
from pathlib import Path
from typing import NamedTuple, Any

from clinictracker.config import TARGET_BASE_URL, TARGET_TZ, BROWSER_CHOICES
from clinictracker.user.models import User, ALLOWED_COLS
from clinictracker.user.config import (
    CommandName,
    ServiceConfig,
    DAYS_BACK_MIN,
    MAX_ITEMS_MIN,
    USERS_JSON_PATH,
)
from clinictracker.startup import (
    QueryParams,
    MyLogger,
    setup_logger,
    get_full_url,
)


# ---------------------------------------------------------------------|
# Query
class QueryParamsForAll(NamedTuple):
    """Query parameters for fetching full lists of all cities.

    Attributes:
        cities (set[str]): Set of cities
        max_days_back (int): Maximum days to look back
        max_nmax (int): Maximum items to collect in full list
    """

    cities: set
    max_days_back: int
    max_nmax: int


def load_query_for_all(users: list[User]) -> QueryParamsForAll:
    cities: list[str] = []
    for user in users:
        cities.extend(user.cities)

    max_user_period = max(user.period for user in users)
    max_user_nmax = max(user.nmax for user in users)

    return QueryParamsForAll(
        cities=set(cities),
        max_days_back=max(DAYS_BACK_MIN, max_user_period + 1),
        max_nmax=max(MAX_ITEMS_MIN, max_user_nmax),
    )


def load_query_for_each(
    config: ServiceConfig, city: str, days_back: int, nmax: int
) -> QueryParams:
    query_dict = {'only_accepting': 'yes', 'list_town': city}
    full_url = get_full_url(config.url, '?', query_dict)
    return QueryParams(
        url=full_url,
        city=city,
        days_back=days_back,
        nmax=nmax,
        tz=config.tz,
    )


# ---------------------------------------------------------------------|
# CLI arguments
USER_ARGS_HINT = (
    "Fields format:\n  username=str nickname=str emails=str,str,... "
    "cities=str,str,... period=int nmax=int\n"
    "username: a unique string\n"
    "nickname: default to null\n"
    "emails: recipients (if not given and username is an email address, "
    "set it as a recipient)\n"
    "cities: town/city list\n"
    "period: schedule period in days (default to 1 or from $PERIOD_USER)\n"
    "nmax: maximum number of items to collect "
    "(default to 10 or from $MAX_ITEMS_USER)\n"
)


def parse_user_args(user_string: str) -> dict:
    """Parses a user string in format:
    'username=str emails=str,str,... ...'
    """
    parts = user_string.split()
    user_data: dict[str, Any] = {}
    for part in parts:
        if '=' in part:
            key, value = [s.strip() for s in part.split('=', maxsplit=1)]
            if key in ['emails', 'cities']:
                # Split comma-separated items
                user_data[key] = [s.strip() for s in value.split(',')]
            else:
                user_data[key] = value

    return user_data


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
        type=str,
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
    subparsers: _SubParsersAction = parser.add_subparsers(
        dest='command',
        metavar='COMMAND',
        help=(
            "Operations to manage user data in the database "
            "(no data fetching and sending)\n"
            f"Valid commands: {', '.join(name for name in CommandName)}"
        ),
    )
    # Subcommand: list
    subparsers.add_parser(CommandName.LIST, description="List all users")
    # Subcommand: add
    add_parser: ArgumentParser = subparsers.add_parser(
        CommandName.ADD,
        description="Insert users (overridden by --load)",
        formatter_class=RawTextHelpFormatter,
    )
    add_parser.add_argument(
        '--user',
        metavar='FIELDS',
        action='append',  # allows multiple --user flags
        type=parse_user_args,
        help=USER_ARGS_HINT,
    )
    # Subcommand: update
    update_parser: ArgumentParser = subparsers.add_parser(
        CommandName.UPD,
        description="Update users (overridden by --load)",
        formatter_class=RawTextHelpFormatter,
    )
    update_parser.add_argument(
        '--user',
        metavar='FIELDS',
        action='append',  # allows multiple --user flags
        type=parse_user_args,
        help=USER_ARGS_HINT,
    )
    # Subcommand: delete
    delete_parser: ArgumentParser = subparsers.add_parser(
        CommandName.DEL,
        description="Delete users (overridden by --load)",
        formatter_class=RawTextHelpFormatter,
    )
    delete_parser.add_argument(
        '--usernames',
        nargs='+',
        type=str,
        metavar='str',
        help="List of usernames",
    )
    subparsers.add_parser(
        CommandName.RESET,
        description=(
            "**CAUTION** Reset user id sequence in database. Perform "
            "after updating from file\n(will prompt for confirmation) "
            "(default: false)"
        ),
        formatter_class=RawTextHelpFormatter,
    )
    subparsers.add_parser(
        CommandName.CLEAR,
        description=(
            "**CAUTION** Empty all tables and reset user id sequence\n"
            "(overridden by --load; will prompt for confirmation) "
            "(default: false)"
        ),
        formatter_class=RawTextHelpFormatter,
    )
    # Table args
    parser.add_argument(
        '--skip-creation',
        action='store_true',
        help="Skip creating tables (default: false)",
    )
    parser.add_argument(
        '--creation-only',
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
            "(default to './data/users.json' or from $USERS_JSON_PATH)"
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
            "(will prompt to confirm) (default: false)"
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
        '--upsert-only',
        action='store_true',
        help=(
            "Exit after updating users without any further operation\n"
            "(no effect if COMMAND is specified) (default: false)"
        ),
    )
    # Sending service args
    parser.add_argument(
        '--send',
        action='store_true',
        help=(
            "Send fetched data to users based on their settings\n"
            "(default: print content to STDOUT without sending)"
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

    args = parser.parse_args()
    validate_args_for_service(args)

    logger = setup_logger(
        name='' if args.debug else __name__,
        is_quiet=args.quiet if not args.debug else False,
    )

    logger.debug(f"Args:\n{vars(args)}")

    match args.command:
        case CommandName.ADD:
            logger.debug(
                "Users to insert:\n"
                + '\n'.join(
                    '-' * 60
                    + f"#{i}\n"
                    + '\n'.join(f"{k:>20}: {user[k]}" for k in ALLOWED_COLS)
                    + '-' * 60
                    for i, user in enumerate(args.user)
                )
            )
        case CommandName.UPD:
            logger.debug(
                "Users to update:\n"
                + '\n'.join(
                    '-' * 60
                    + f"#{i}\n"
                    + '\n'.join(f"{k:>20}: {v}" for k, v in user)
                    + '-' * 60
                    for i, user in enumerate(args.user)
                )
            )
        case CommandName.DEL:
            logger.debug(f"Users to delete: {args.username}")

    return args, logger


def validate_args_for_service(args: Namespace) -> None:
    """Validates CLI arguments.
    User fields will be validated when creating User objects.
    """
    if not args.url.strip():
        raise ValueError("Missing URL. See --help")

    if (args.load or args.save) and not args.file:
        raise ValueError("A file path must be specified by -f/--file.")

    if args.command in [CommandName.ADD, CommandName.UPD] and not args.user:
        raise ValueError("No user data provided.")

    if args.command == CommandName.DEL and not args.usernames:
        raise ValueError("No usernames provided.")
