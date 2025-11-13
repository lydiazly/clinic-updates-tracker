# -*- coding: utf-8 -*-
# utils.py
"""Generic utility functions."""

from bs4 import BeautifulSoup

# from bs4.element import Tag, PageElement
from datetime import datetime, timedelta, timezone, date, tzinfo, time
from dateutil.parser import parse, ParserError
from logging import Logger
import nh3
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from clinictracker.models import ItemData
from clinictracker.startup import QueryParams, MyLogger, default_logger


# DATE_FMT = '%B %d, %Y'
# DATE_UTC_FMT = '%Y-%m-%d (UTC)'
DATETIME_FMT = '%Y-%m-%d %H:%M:%S'
DATETIME_TZ_FMT = DATETIME_FMT + ' (%Z)'
DATETIME_UTC_FMT = '%Y-%m-%dT%H:%M:%SZ'

TITLE_TEMPLATE = "{city} clinic updates in the past {days}"
SEE_MORE = "Go to website to view full list"


def print_error(
    exc: Exception | BaseException,
    logger: Logger | MyLogger = default_logger,
    max_level: int = 5,
) -> None:
    """Prints error messages and causes."""
    current_exc = exc
    level = 1
    while current_exc is not None and level <= max_level:
        logger.error(f"{'  └─ ' if level > 1 else ''}{current_exc}")
        if current_exc.__cause__ is not None:
            current_exc = current_exc.__cause__
            level += 1
        elif current_exc.__context__ is not None:
            current_exc = current_exc.__context__
            level += 1
        else:
            return


def sanitize_content(html_content: str) -> str:
    """Sanitizes HTML content while preserving certain tags."""
    allowed_tags = {'br', 'p', 'strong', 'i', 'b', 'a', 'em'}
    soup = BeautifulSoup(html_content, 'html.parser')
    # Join spaces, tabs, and new lines in each element ----------------|
    raw_html = '\n'.join(
        re.sub(r"\s+", ' ', str(elem)).strip() for elem in soup
    )
    # Sanitize while keeping allowed tags -----------------------------|
    sanitized_content = nh3.clean(raw_html, tags=allowed_tags)
    # Trim each line
    sanitized_content = '\n'.join(
        s.strip() for s in sanitized_content.split('\n') if s.strip()
    )
    # Remove any empty '<p></p>' --------------------------------------|
    sanitized_content = re.sub(r"(<p>\s*</p>)+", '', sanitized_content)
    # '<p>...</p>' --> '<br>...<br>' ----------------------------------|
    # sanitized_content = re.sub(
    #     r"[ \t]*<p>|</p>[ \t]*", "<br>", sanitized_content
    # )
    # Multiple <br> or <br /> --> <br> --------------------------------|
    sanitized_content = re.sub(
        r"([ \t]*<br\s*/?>[ \t]*)+", '<br>', sanitized_content
    )
    # Remove leading and trailing <br> or <br /> ----------------------|
    sanitized_content = re.sub(
        r'^[ \t]*(<br\s*/?>)+|(<br\s*/?>)+[ \t]*$', '', sanitized_content
    )
    return sanitized_content


def html_to_plain(html_content: str, indent: str = '') -> str:
    """Converts HTML to plain text. Removes extra links."""
    remove_list = [
        "Clinic Website",
        "Website",
        "Contact Information & Map",
        "Contact",
    ]
    soup = BeautifulSoup(html_content, 'html.parser')
    # Find all <a> tags and remove if matches any of remove_list
    for tag in soup.find_all('a'):
        if tag.string and tag.string.strip() in remove_list:
            tag.decompose()
    text = soup.get_text(f"\n{indent}", strip=True)
    return text


def construct_content(
    items: list[ItemData],
    n_tot: int,
    query: QueryParams,
    full_html: bool = True,
) -> str:
    """Constructs HTML content and concatenates into a string."""
    if len(items) == 0:
        return ''

    title = TITLE_TEMPLATE.format(
        city=query.city, days=days_str(query.days_back)
    )
    lines = [f"<h2>{title}</h2>"]
    lines.append("<ol>")
    for item in items:
        lines.append(
            "<li><strong>"
            f'<a href="{item.url}">{item.title}</a>'
            f" (Posted {item.date if item.date else 'Unknown'})"
            "</strong></li>"
        )
        lines.append(item.content)
    if len(items) < n_tot:
        lines.append(
            f'<p><a href="{query.url}">' f"<em>{SEE_MORE}</em>" "</a></p>"
        )
    lines.append("</ol>")
    if full_html:
        lines = (
            ["<!DOCTYPE html>", "<html>", "<head>"]
            + ['<meta charset="utf-8">', f"<title>{title}</title>"]
            + ["</head>", "<body>"]
            + lines
            + ["</body>", "</html>"]
        )
    return '\n'.join(lines)


def print_content(
    items: list[ItemData],
    n_tot: int,
    query: QueryParams,
    to_stdout: bool = True,
) -> str:
    """Returns content as plain text. Prints to STDOUT if `to_stdout`."""
    lines: list[str] = []
    indent: str = '  '
    if len(items) > 0:
        title = TITLE_TEMPLATE.format(
            city=query.city, days=days_str(query.days_back)
        )
        lines.append('\n# ' + title)
        for i, item in enumerate(items):
            lines.append(f"\n{indent}{i + 1}.")
            if item.url:
                lines.append(f"{indent}{item.url}")
            lines.append(
                f"{indent}{item.title}"
                f" (Posted {item.date if item.date else 'Unknown'})"
            )
            lines.append(indent + html_to_plain(item.content, indent))
        if len(items) < n_tot:
            lines.append(f"\n{indent}--> {SEE_MORE}:\n{query.url}\n")
    else:
        lines.append("Nothing to print.")

    text: str = '\n'.join(lines)
    if to_stdout:
        print(text)

    return text


def is_date_within(
    target_date: str | datetime | date,
    days_back: int,
    ref_datetime: datetime | None = None,
    tz: str = '',
    logger: Logger | MyLogger = default_logger,
) -> bool:
    """Checks if a given date is within the past n days.
    1-hour buffer time before ref_datetime is applied.

    Args:
        target_date (str | datetime | date): the date to be checked,
            assuming at noon if no time specified (can be naive)
        days_back (int): number of days up to now
        ref_datetime (datetime): reference time to compare,
            default to now (naive)
        tz (str): time zone of the target_date, default to local time zone

    Returns:
        is_within (bool): Is within the past n days or not

    Raises:
        ValueError: If the date string is empty or unable to be parsed
    """
    if not target_date or (
        isinstance(target_date, str) and not target_date.strip()
    ):
        raise ValueError("(is_date_within) Target date is missing.")

    if ref_datetime is None:
        ref_datetime = datetime.now().astimezone()  # timezone-aware

    # Prepare reference time ------------------------------------------|
    # Preset time (**adjust this if needed**)
    ref_time: time = time(12, 0, 0)
    # ref_time_str: str = ref_time.strftime('%H:%M:%S')

    buffer: timedelta = timedelta(hours=1)

    # Presumed to be in the current system's local time zone
    ref_local: datetime = (
        ref_datetime.astimezone()
        if ref_datetime.tzinfo is None
        else ref_datetime
    )  # timezone-aware

    # Apply a buffer
    ref_local -= buffer

    if ref_local.tzname() == 'UTC':
        ref_str_all = ref_local.strftime(DATETIME_UTC_FMT)
    else:
        ref_local_str = ref_local.strftime(DATETIME_TZ_FMT)
        # Note: '%Z' may be different from the TZ name
        # Get reference time in UTC (for logging only)
        ref_utc: datetime = ref_local.astimezone(timezone.utc)
        ref_utc_str = ref_utc.strftime(DATETIME_UTC_FMT)
        ref_str_all = f"{ref_local_str} ({ref_utc_str})"

    # Verify TZ info --------------------------------------------------|
    tz_info: ZoneInfo | tzinfo | None = None
    tzname: str
    # Use provided TZ identifier/name for target time
    if tz:
        try:
            tz_info = ZoneInfo(tz.strip())  # <class 'zoneinfo.ZoneInfo'>
            tzname = tz_info.key  # or str(tz_info)
        except ZoneInfoNotFoundError:
            # Set to the local time zone later
            logger.warning(f"Time zone not found: {tz}")

    if tz_info is None:
        # If the object includes tzinfo, use it
        if (
            isinstance(target_date, datetime)
            and target_date.tzinfo is not None
        ):
            tz_info = target_date.tzinfo
            tzname = target_date.tzname() or 'Unknown'
        # Otherwise, use the local time zone
        else:
            tz_info = ref_local.tzinfo  # <class 'datetime.timezone'>
            tzname = ref_local.tzname() or 'Unknown'
            logger.warning("Applying local time zone to the target time.")

    # Parse target time -----------------------------------------------|
    target_parsed: datetime  # timezone-aware
    try:
        if isinstance(target_date, str):
            # Parse the string using dateutil.parser.parse
            target_parsed = parse(
                target_date,
                default=datetime.combine(
                    datetime.today(), ref_time.replace(tzinfo=tz_info)
                ),  # use this time and tz if not specified
            )
        elif isinstance(target_date, datetime):
            target_parsed = target_date.astimezone(tz_info)
        elif isinstance(target_date, date):
            target_parsed = datetime.combine(
                target_date, ref_time.replace(tzinfo=tz_info)
            )
        else:
            raise TypeError(
                "Target date must be a string, datetime, or date object."
            )
    except (ParserError, TypeError) as e:
        raise ParserError(f"(is_date_within) Error parsing date:\n{e}") from e

    if tzname == 'UTC':
        target_str_all = target_parsed.strftime(DATETIME_UTC_FMT)
    else:
        target_str_with_tz = (
            f"{target_parsed.strftime(DATETIME_FMT)} ({tzname})"
        )
        # Convert to UTC (for logging only)
        target_utc: datetime = target_parsed.astimezone(timezone.utc)
        target_utc_str = target_utc.strftime(DATETIME_UTC_FMT)
        target_str_all = f"{target_str_with_tz} ({target_utc_str})"

    # Compare dates ---------------------------------------------------|
    # Automatically handles timezone conversion for timezone-aware objects
    time_diff: timedelta = ref_local - target_parsed
    # days_diff: int = time_diff.days
    days_diff: float = time_diff.total_seconds() / 3600 / 24
    is_within: bool = days_diff <= days_back

    if is_within:
        logger.debug(
            f"{target_str_all} is within {days_str(days_back)} before "
            f"{ref_str_all}. Collecting..."
        )
    else:
        logger.debug(
            f"{target_str_all} is {days_str(days_diff)} earlier than "
            f"{ref_str_all}. Returning..."
        )

    return is_within


def days_str(days: int | float) -> str:
    "Returns '1 day' or 'N days'"
    _days = f"{days:.3g}" if isinstance(days, float) else str(days)
    return f"{_days} day{'' if _days == '1' else 's'}"
