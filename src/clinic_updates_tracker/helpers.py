# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/helpers.py
from bs4 import BeautifulSoup
import argparse
from datetime import datetime, timezone
from dateutil import parser
import logging
import re
import sys
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import OUTPUT_NAME, TARGET_BASE_URL, TARGET_TZ, CITY, DAYS_SINCE, MAX_N_ITEMS, BROWSER_CHOICES


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
        '--tz',
        type=str,
        metavar='str',
        default=TARGET_TZ,
        help="time zone identifier of the target website (empty means native) (default: %(default)s)"
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
        help="path of output file. Empty indicates no export. (default: %(default)s)"
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
        '--debug',
        action='store_true',
        help="print debug logs"
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


def construct_content(
    item_list: list[dict], page_url: str, city: str, n_days: int, nmax: int, ntot: int
) -> list[str]:
    """Constructs HTML content as lines."""
    if len(item_list) == 0:
        return []

    title = f"Updates regarding {city} in the past {n_days} days"
    lines = [f"<h2>{title}</h2>"]
    lines.append(f"<p><strong>Showing first {nmax} updates:</strong></p>")
    lines.append("<ol>")
    for item in item_list:
        lines.append(
            "<li><strong>"
            + f"<a href=\"{item['url']}\">{item['title']}</a>"
            + f" (Posted {item['date']})"
            + "</strong></li>"
        )
        lines.append(item['content'])
    if len(item_list) < ntot:
        lines.append(f"<p><a href=\"{page_url}\"><em>Go to website to view full list</em></a></p>")
    lines.append("</ol>")
    lines = (
        ["<!DOCTYPE html>", "<html>", "<head>"]
        + ['<meta charset="utf-8">', f"<title>{title}</title>"]
        + ["</head>", "<body>"]
        + lines
        + ["</body>", "</html>"]
    )
    return lines


def is_date_within_n_days(date_str: str, n_days: int, tz: str = '') -> tuple[bool, str, bool]:
    """Checks if a given date string in any format is within n days before the reference time."""
    if not date_str:
        return False, "Error parsing date: date string is empty.", False

    # Get current date (native) for getting local time zone
    now_naive = datetime.now()  # native datetime
    now_local = now_naive.astimezone()  # presumed to be local time
    # now_naive_str = now_local.strftime('%B %d, %Y (%Z)')  # %Z: timezone name, not identifier
    # Get current time in UTC (for checking)
    now_utc = datetime.now(timezone.utc)  # timezone-aware
    now_date_utc = now_utc.date()
    now_utc_str = now_date_utc.strftime('%Y-%m-%d (UTC)')
    # now_str_all = f"{now_naive_str} / {now_utc_str}"

    msg = ''
    tzinfo = None
    # Use provided time zone string
    if tz:
        try:
            tzinfo = ZoneInfo(tz.strip())  # <class 'zoneinfo.ZoneInfo'>
            tzname = tzinfo.key  # or str(tzinfo)
        except ZoneInfoNotFoundError as e:
            msg = f"WARNING: {e}. Using local time zone...\n"
        else:
            # Convert to target timezone
            # now_target = now_utc.astimezone(tzinfo)
            now_target = now_local.astimezone(tzinfo)
    # Or use local timezone
    if tzinfo is None:
        tzinfo = now_local.tzinfo  # <class 'datetime.timezone'>
        tzname = str(tzinfo)
        now_target = now_local  # assume same timezone as target

    now_date_target = now_target.date()
    now_target_str = now_target.strftime('%B %d, %Y (%Z)')  # %Z: timezone name, not identifier
    now_str_all = f"{now_target_str} / {now_utc_str}"

    try:
        # Parse the date string (no time) using dateutil.parser with the determined timezone
        ref_time_str = ' 12:00:00'  # preset, adjust this if needed
        parsed_datetime = parser.parse(date_str + ref_time_str, default=datetime.now(tzinfo))  # timezone-aware
        parsed_date = parsed_datetime.date()
        date_str_with_tz = f"{date_str} ({tzname})"
        # Convert to UTC (for checking)
        parsed_date_utc = parsed_datetime.astimezone(timezone.utc).date()
        date_utc_str = parsed_date_utc.strftime('%Y-%m-%d (UTC)')
        date_str_all = f"{date_str_with_tz} / {date_utc_str}"

        # Convert ref_time to datetime object
        # ref_datetime = datetime.fromtimestamp(ref_time)
        # ref_date_str = ref_datetime.strftime('%B %d, %Y')

        # Calculate the earliest date (n days before ref_datetime)
        # min_datetime = ref_datetime - timedelta(days=n_days)

        # Calculate the days between ref_datetime and parsed_datetime
        # Check if parsed_datetime is within the range (between min_datetime and ref_datetime)
        # is_within = min_datetime <= parsed_datetime <= ref_datetime

        # Compare the date
        # days_diff = (now_date_utc - parsed_date_utc).days  # use UTC dates
        days_diff = (now_date_target - parsed_date).days  # use target timezone
        is_within = days_diff <= n_days
        # Note: Because ref_time_str is preset, days_diff might be less than 0

        if is_within:
            msg += f"{date_str_all} is within {n_days} days before {now_str_all}. Collecting..."
        else:
            msg += f"{date_str_all} is {days_diff} day{'s' if days_diff > 1 else ''} earlier than {now_str_all}. Returning..."
        return True, msg, is_within

    except (ValueError, TypeError) as e:
        return False, f"Error parsing date '{date_str}': {e}", False
