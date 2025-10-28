# -*- coding: utf-8 -*-
# startup.py
"""Logger setter and CLI argument parsers."""
from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from enum import StrEnum  # python 3.11+
import logging
from pathlib import Path
import sys
from typing import Any, NamedTuple
from urllib.parse import urlencode

from clinictracker.config import (
    TARGET_BASE_URL,
    TARGET_TZ,
    CITY,
    DAYS_BACK,
    MAX_ITEMS,
    BROWSER_CHOICES,
    OUTPUT_HTML_PATH,
)


def trim_str(s: str) -> str:
    """Removes leading and trailing spaces and quotes."""
    return s.strip().strip('"').strip("'")


# ---------------------------------------------------------------------|
# Query
class QueryParams(NamedTuple):
    """Query parameters.

    Attributes:
        url (str): The target full URL
        city (str): The town/city to be queried
        days_back (int): Number of days to look back for data collection
        nmax (int): Maximum number of items to collect
        tz (str): TZ identifier (IANA Time Zones) of the target website
    """

    url: str
    city: str
    days_back: int
    nmax: int
    tz: str


def load_query(args: Namespace) -> QueryParams:
    """Constructs query parameters."""
    # Constructs full target URL.
    # Note: argument 'only_accepting' only affects the clinic table
    #       but not the update list
    query_dict = ({'only_accepting': 'yes'} if not args.all else {}) | {
        'list_town': args.city
    }
    full_url = get_full_url(trim_str(args.url), '?', query_dict)
    query = QueryParams(
        url=full_url,
        city=trim_str(args.city),
        days_back=args.days,
        nmax=args.nmax,
        tz=trim_str(args.tz),
    )
    return query


# ---------------------------------------------------------------------|
# Logging
class Color(StrEnum):
    """Preset ANSI color escape codes: GRAY, YELLOW, RED, RED_B, END"""

    GRAY = '\x1b[90m'
    YELLOW = '\x1b[33m'
    RED = '\x1b[31m'
    RED_B = '\x1b[31;1m'
    END = '\x1b[0m'


class MyLogger:
    def __init__(self, logger: logging.Logger, is_quiet: bool = False):
        self.logger = logger
        self.is_quiet = is_quiet

    def info(self, msg: str) -> None:
        if not self.is_quiet:
            self.logger.info(msg)

    # Delegate everything else
    def __getattr__(self, name: str) -> Any:
        return getattr(self.logger, name)


class CustomInfoFormatter(logging.Formatter):
    FMT = "[%(levelname)s] %(message)s"
    FORMATTERS = {
        logging.DEBUG: logging.Formatter(Color.GRAY + FMT + Color.END),
        logging.INFO: logging.Formatter(FMT),
        logging.WARNING: logging.Formatter(Color.YELLOW + FMT + Color.END),
        logging.ERROR: logging.Formatter(Color.RED + FMT + Color.END),
        logging.CRITICAL: logging.Formatter(Color.RED_B + FMT + Color.END),
    }

    def format(self, record):
        formatter = self.FORMATTERS.get(record.levelno)
        return formatter.format(record)


class CustomDebugFormatter(logging.Formatter):
    """Logging Formatter for --debug to add colors and count warning / errors"""

    FMT1 = "[%(asctime)s %(levelno)s] %(message)s"
    FMT2 = "[%(asctime)s %(levelno)s] (%(levelname)s) %(message)s (%(filename)s:%(lineno)d)"
    FORMATTERS = {
        logging.DEBUG: logging.Formatter(Color.GRAY + FMT1 + Color.END),
        logging.INFO: logging.Formatter(FMT1),
        logging.WARNING: logging.Formatter(Color.YELLOW + FMT2 + Color.END),
        logging.ERROR: logging.Formatter(Color.RED + FMT2 + Color.END),
        logging.CRITICAL: logging.Formatter(Color.RED_B + FMT2 + Color.END),
    }

    def format(self, record):
        formatter = self.FORMATTERS.get(record.levelno)
        return formatter.format(record)


def setup_logger(
    name: str = '', is_quiet: bool = False
) -> logging.Logger | MyLogger:
    """Sets and returns a logger."""
    if name:
        # Level: INFO, use a local logger with a name
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setLevel(logging.INFO)
        # formatter = logging.Formatter("[%(levelname)s] %(message)s")
        # handler.setFormatter(formatter)
        handler.setFormatter(CustomInfoFormatter())
        logger.addHandler(handler)
        logger.propagate = False
        # Suppress urllib3 warnings
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        # Wrap the logger
        return MyLogger(logger, is_quiet)
    else:
        # Level: DEBUG, use the root logger
        # Create handler with custom formatter
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(CustomDebugFormatter())
        logging.basicConfig(
            level=logging.DEBUG,
            handlers=[handler],
        )
        logger = logging.getLogger()
        return logger


# ---------------------------------------------------------------------|
# CLI arguments
def get_args_and_logger() -> tuple[Namespace, logging.Logger | MyLogger]:
    """Gets CLI arguments and sets the logger."""
    parser = ArgumentParser(
        usage="%(prog)s [-h] [options] [town/city]",
        description=(
            "Fetches clinic updates across a specified region "
            "from a target website."
        ),
        formatter_class=RawTextHelpFormatter,
    )
    # Query args
    parser.add_argument(
        'city',
        type=str,
        nargs='?',
        metavar='town/city',
        default=CITY,
        help="The town/city to be queried (default from $CITY)",
    )
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
    parser.add_argument(
        '-d',
        '--days',
        type=int,
        metavar='int',
        default=DAYS_BACK,
        help=(
            "Number of days to look back for data collection "
            "(default to 1 or from $DAYS_BACK)"
        ),
    )
    parser.add_argument(
        '-n',
        '--nmax',
        type=int,
        metavar='int',
        default=MAX_ITEMS,
        help=(
            "Maximum number of items to collect "
            "(default to 10 or from $MAX_ITEMS)"
        ),
    )
    parser.add_argument(
        '-a',
        '--all',
        action='store_true',
        help=(
            "Include all clinics (no effect - only affects the clinic table "
            "but not the update list)"
        ),
    )
    # Output args
    parser.add_argument(
        '-p',
        '--print',
        dest='to_stdout',
        action='store_true',
        help="Print results as plain text to STDOUT (default: false)",
    )
    parser.add_argument(
        '-o',
        '--output',
        type=Path,
        metavar='str',
        default=OUTPUT_HTML_PATH,
        help=(
            "Path of output file (default to './output/content.html' "
            "or from $OUTPUT_HTML_PATH)"
        ),
    )
    parser.add_argument(
        '--no-o',
        dest='export',
        action='store_false',
        help="No export (default: export to a file)",
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
            "Exit after opening a page without any further operation "
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
    validate_args(args)

    logger = setup_logger(
        name='' if args.debug else __name__,
        is_quiet=args.quiet if not args.debug else False,
    )

    logger.debug(f"Args:\n{vars(args)}")

    return args, logger


def validate_args(args: Namespace) -> None:
    """Validates CLI arguments."""
    if not trim_str(args.url):
        raise ValueError("Missing URL. See --help")

    if not trim_str(args.city):
        raise ValueError("Missing town/city. See --help")

    if args.days <= 0:
        raise ValueError("Value of -d/--days must be positive.")

    if args.nmax <= 0:
        raise ValueError("Value of -n/--nmax must be positive.")


def get_full_url(
    base_url: str, delim: str = '?', sub: dict[str, str] | str = {}
) -> str:
    """Appends `sub` (a query dict or a subdirectory string) to the base URL:
    `{base_url}?arg1=val1&...` or `{base_url}/...`"""
    # Query
    if delim == '?' and isinstance(sub, dict):
        full_url = f"{base_url}?{urlencode(sub)}"
        # will encode special characters as well
    # Subdirectory
    else:
        full_url = f"{base_url.rstrip('/')}/{str(sub)}"
    return full_url
