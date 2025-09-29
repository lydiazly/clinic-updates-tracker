# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/helpers.py
from bs4 import BeautifulSoup
import argparse
from datetime import datetime, timedelta
from dateutil import parser
import logging
import re
import sys
from urllib.parse import urlencode

from . import OUTPUT_NAME, TARGET_BASE_URL, CITY, DAYS_SINCE, MAX_N_ITEMS, BROWSER_CHOICES


def get_full_url(base_url: str, delim: str = '?', sub: dict | str = {}) -> str:
    """Appends `sub` (a query dict or a subdirectory string) to the base URL:
    {base_url}?arg1=val1&... or {base_url}/..."""
    if delim == '?' and isinstance(sub, dict):  # query
        full_url = f"{base_url}?{urlencode(sub)}"  # will encode special characters as well
    else:  # subdirectory
        full_url = f"{base_url}/{str(sub)}"
    return full_url


def setup_logger(name: str = '') -> logging.Logger:
    """Sets and returns the logger."""
    if name:
        # Level=INFO, use a local logger with a name
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
        # Suppress urllib3 warnings
        logging.getLogger("urllib3").setLevel(logging.ERROR)
    else:
        # Level=DEBUG, use the root logger
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelno)s - %(message)s")
        logger = logging.getLogger()
    return logger


def get_options() -> tuple[argparse.Namespace, logging.Logger]:
    """Gets options from user and sets the logger."""

    parser = argparse.ArgumentParser(
        description="Check updates on target URL."
    )
    parser.add_argument(
        'city',
        type=str,
        nargs="?",
        metavar='town/city',
        default=CITY,
        help="target town/city (default: %(default)s)"
    )
    parser.add_argument(
        '--url',
        type=str,
        metavar='str',
        default=TARGET_BASE_URL,
        help="target URL (default: %(default)s)"
    )
    parser.add_argument(
        '-d', '--days',
        type=int,
        metavar='int',
        default=DAYS_SINCE,
        help="only show items within these days (default: %(default)s)"
    )
    parser.add_argument(
        '-n', '--nmax',
        type=int,
        metavar='int',
        default=MAX_N_ITEMS,
        help="only show first n items (default: %(default)s)"
    )
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help="get all updates (only affects the clinic table but not the update list)"
    )
    parser.add_argument(
        '-p', '--print',
        action='store_true',
        help="print result as plain text to STDOUT"
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        metavar='str',
        default=OUTPUT_NAME,
        help="path of output file (default: %(default)s)"
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help="still show errors but suppress info output in stderr, unless --test or --debug is set"
    )
    parser.add_argument(
        '-H', '--headed',
        action='store_true',
        help="run in headed mode (default: headless)"
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help="print debug logs"
    )
    parser.add_argument(
        '-b', '--browser',
        metavar='str',
        choices=BROWSER_CHOICES,
        default='chromium',
        help="specify a browser. Choices: %(choices)s (default: %(default)s)"
    )
    parser.add_argument(
        '--headless-shell',
        dest='shell',
        action='store_true',
        help="use a separate headless shell for chromium headless mode (see https://playwright.dev/python/docs/browsers#chromium-headless-shell)"
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help="test the browser without any page operation"
    )
    args = parser.parse_args()

    # Note: argument 'only_accepting' only affects the clinic table but not the update list
    query_dict = ({'only_accepting': 'yes'} if not args.all else {}) | {'list_town': args.city}
    target_url = get_full_url(args.url, '?', query_dict)

    logger = setup_logger('' if args.debug else __name__)

    return args, logger, target_url


def preserve_tags(element) -> str:
    """Extracts the textual content of an HTML element while preserving certain tags."""
    if element.name in ['br', 'p', 'i', 'b', 'a', 'em']:
        text = str(element)
    else:
        text = element.get_text()
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return text


def clear_content(content: str) -> str:
    """Clears content."""
    soup = BeautifulSoup(content, 'html.parser')
    cleared_content = "\n".join(s.strip() for s in map(preserve_tags, soup) if s.strip())
    cleared_content = re.sub(r"(<p>\s*</p>)+", "", cleared_content)  # remove any empty '<p></p>'
    # cleared_content = re.sub(r"[ \t]*<p>|</p>[ \t]*", "<br>", cleared_content)  # '<p>...</p>' --> '<br>...<br>'
    cleared_content = re.sub(r"([ \t]*<br\s*/?>[ \t]*)+", "<br>", cleared_content)  # multiple <br> or <br /> --> <br>
    cleared_content = re.sub(r'^[ \t]*(<br\s*/?>)+|(<br\s*/?>)+[ \t]*$', '', cleared_content)  # remove leading and trailing <br> or <br />
    return cleared_content


def is_date_within_n_days(date_str: str, ref_time: float, n_days: int) -> tuple[bool, str, bool]:
    """Checks if a given date string in any format is within n days before the reference time."""
    if not date_str:
        return False, "Error parsing date: date string is empty.", False

    try:
        # Parse the date string using dateutil.parser (handles many formats)
        parsed_date = parser.parse(date_str)
        # Convert ref_time to datetime object
        ref_datetime = datetime.fromtimestamp(ref_time)
        ref_date_str = ref_datetime.strftime('%B %d, %Y')
        # Calculate the earliest date (n days before ref_datetime)
        min_datetime = ref_datetime - timedelta(days=n_days)
        # Check if parsed_date is within the range (between min_datetime and ref_datetime)
        is_within = min_datetime <= parsed_date <= ref_datetime
        return (
            True,
            (
                f"{date_str} is within {n_days} days before {ref_date_str}. Collecting..." if is_within
                else f"{date_str} is {n_days} days earlier than {ref_date_str}. Returning..."
            ),
            is_within,
        )

    except (ValueError, TypeError) as e:
        return False, f"Error parsing date '{date_str}': {e}", False
