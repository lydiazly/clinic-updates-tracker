# -*- coding: utf-8 -*-
# startup.py
"""Logger setter and CLI argument parsers."""
from argparse import ArgumentParser, Namespace
import logging
from pathlib import Path
import sys
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
from clinictracker.models import QueryParams


def setup_logger(name: str = '') -> logging.Logger:
    """Sets and returns a logger."""
    if name:
        # Level: INFO, use a local logger with a name
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
        # Suppress urllib3 warnings
        logging.getLogger('urllib3').setLevel(logging.ERROR)
    else:
        # Level: DEBUG, use the root logger
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelno)s - %(message)s",
        )
        logger = logging.getLogger()
    return logger


def validate_args(args: Namespace) -> None:
    """Validates CLI arguments."""
    if not args.url.strip():
        raise ValueError("Missing URL. See --help")

    if not args.city.strip():
        raise ValueError("Missing town/city. See --help")

    if args.days <= 0:
        raise ValueError("Value of -d/--days must be positive.")

    if args.nmax <= 0:
        raise ValueError("Value of -n/--nmax must be positive.")


def get_args_and_logger() -> tuple[Namespace, logging.Logger]:
    """Gets CLI arguments and sets the logger."""

    parser = ArgumentParser(
        description="Check updates on target website."
    )
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
            "TZ identifier (IANA Time Zones) of the target website "
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
            "(default to 1 or from $MAX_ITEMS)"
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
            "Path of output file (empty is interpreted as '.') "
            "(default to './output/content.html' or from $OUTPUT_HTML_PATH)"
        ),
    )
    parser.add_argument(
        '--no-o',
        dest='export',
        action='store_false',
        help="No export (default: export to a file)",
    )
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
            "Use a separate headless shell for chromium headless mode "
            "(https://playwright.dev/python/docs/browsers#chromium-headless-shell)"
        ),
    )
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
            "Suppress INFO level outputs unless selecting "
            "--test or --debug (default: print all)"
        ),
    )
    args = parser.parse_args()

    logger = setup_logger('' if args.debug else __name__)

    validate_args(args)

    logger.debug(f"Arguments: {args}")

    return args, logger


def get_full_url(base_url: str, delim: str = '?', sub: dict | str = {}) -> str:
    """Appends `sub` (a query dict or a subdirectory string) to the base URL:
    `{base_url}?arg1=val1&...` or `{base_url}/...`"""
    # Query
    if delim == '?' and isinstance(sub, dict):
        full_url = f"{base_url}?{urlencode(sub)}"
        # will encode special characters as well
    # Subdirectory
    else:
        full_url = f"{base_url}/{str(sub)}"
    return full_url


def load_query(args: Namespace) -> QueryParams:
    """Constructs query parameters."""
    # Constructs full target URL.
    # Note: argument 'only_accepting' only affects the clinic table but not the update list
    query_dict = ({'only_accepting': 'yes'} if not args.all else {}) | {
        'list_town': args.city
    }
    full_url = get_full_url(args.url, '?', query_dict)
    query = QueryParams(
        url=full_url,
        city=args.city,
        days_back=args.days,
        nmax=args.nmax,
        tz=args.tz,
    )
    return query
