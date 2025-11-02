# -*- coding: utf-8 -*-
# utils.py
"""Generic utility functions."""
from bs4 import BeautifulSoup
from bs4.element import Tag, PageElement
from datetime import datetime, timedelta, timezone, date, tzinfo, time
from dateutil.parser import parse, ParserError
from logging import Logger, getLogger
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from clinictracker.models import ItemData
from clinictracker.startup import QueryParams, MyLogger


TITLE_TEMPLATE = "%(city)s clinic updates in the past %(days_back)s days"


def print_error(
    exc: Exception | BaseException,
    logger: Logger | MyLogger,
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


def preserve_tags(element: PageElement) -> str:
    """Extracts the textual content of an HTML element while
    preserving certain tags.
    """
    keep_tag_list = ['br', 'p', 'i', 'b', 'a', 'em']
    if isinstance(element, Tag) and element.name not in keep_tag_list:
        text = element.get_text()
    else:
        text = str(element)
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return text


def clear_content(html_content: str) -> str:
    """Clears HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    cleared_content = '\n'.join(
        s.strip() for s in map(preserve_tags, soup) if s.strip()
    )
    # Remove any empty '<p></p>' --------------------------------------|
    cleared_content = re.sub(r"(<p>\s*</p>)+", "", cleared_content)
    # '<p>...</p>' --> '<br>...<br>' ----------------------------------|
    # cleared_content = re.sub(
    #     r"[ \t]*<p>|</p>[ \t]*", "<br>", cleared_content
    # )
    # Multiple <br> or <br /> --> <br> --------------------------------|
    cleared_content = re.sub(
        r"([ \t]*<br\s*/?>[ \t]*)+", "<br>", cleared_content
    )
    # Remove leading and trailing <br> or <br /> ----------------------|
    cleared_content = re.sub(
        r'^[ \t]*(<br\s*/?>)+|(<br\s*/?>)+[ \t]*$', '', cleared_content
    )
    return cleared_content


def html_to_plain(html_content: str) -> str:
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
    text = soup.get_text('\n', strip=True)
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

    title = TITLE_TEMPLATE % query._asdict()
    lines = [f"<h2>{title}</h2>"]
    lines.append("<ol>")
    for item in items:
        lines.append(
            "<li><strong>"
            f'<a href="{item.url}">{item.title}</a>'
            f" (Posted {item.date if item.date else 'Unknown'})"
            "</strong></li>"
        )
        if item.content:
            lines.append(item.content)
    if len(items) < n_tot:
        lines.append(
            f'<p><a href="{query.url}">'
            "<em>Go to website to view full list</em>"
            "</a></p>"
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
    items: list[ItemData], n_tot: int, query: QueryParams
) -> None:
    """Prints content as plain text to STDOUT."""
    if len(items) > 0:
        print("\n" + TITLE_TEMPLATE % query._asdict() + ":\n")
        for i, item in enumerate(items):
            print(f"{i + 1}.")
            if item.url:
                print(f"{item.url}")
            print(f"{item.title}")
            print(f"(Date: {item.date if item.date else 'Unknown'})")
            if item.content:
                print(html_to_plain(item.content))
            print('')
        if len(items) < n_tot:
            print(f"--> Go to website to view full list:\n{query.url}\n")
    else:
        print("Nothing to print.")


def is_date_within(
    target_date: str | datetime | date,
    days_back: int,
    ref_datetime: datetime | None = None,
    tz: str = '',
    logger: Logger | MyLogger = getLogger(),
) -> bool:
    """Checks if a given date is within the past n days.
    1-hour buffer is considered.

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

    # date_fmt = '%B %d, %Y'
    # date_utc_fmt = '%Y-%m-%d (UTC)'
    datetime_fmt = '%Y-%m-%d %H:%M:%S'
    datetime_utc_fmt = '%Y-%m-%dT%H:%M:%SZ'

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
        ref_str_all = ref_local.strftime(datetime_utc_fmt)
    else:
        ref_local_str = ref_local.strftime(datetime_fmt + ' (%Z)')
        # Note: '%Z' may be different from the TZ name
        # Get reference time in UTC (for logging only)
        ref_utc: datetime = ref_local.astimezone(timezone.utc)
        ref_utc_str = ref_utc.strftime(datetime_utc_fmt)
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
        raise ParserError(f"(is_date_within) Error parsing date:\n{e}")
    else:
        if tzname == 'UTC':
            target_str_all = target_parsed.strftime(datetime_utc_fmt)
        else:
            target_str_with_tz = (
                f"{target_parsed.strftime(datetime_fmt)} ({tzname})"
            )
            # Convert to UTC (for logging only)
            target_utc: datetime = target_parsed.astimezone(timezone.utc)
            target_utc_str = target_utc.strftime(datetime_utc_fmt)
            target_str_all = f"{target_str_with_tz} ({target_utc_str})"

    # Compare dates ---------------------------------------------------|
    # Automatically handles timezone conversion for timezone-aware objects
    time_diff: timedelta = ref_local - target_parsed
    # days_diff: int = time_diff.days
    days_diff: float = time_diff.total_seconds() / 3600 / 24
    is_within: bool = days_diff <= days_back

    days_diff_str = f"{days_diff:.3g}"
    _days = 'day' if days_diff_str == '1' else 'days'
    if is_within:
        logger.debug(
            f"{target_str_all} is within {days_back} {_days} before "
            f"{ref_str_all}. Collecting..."
        )
    else:
        logger.debug(
            f"{target_str_all} is {days_diff_str} {_days} earlier than "
            f"{ref_str_all}. Returning..."
        )

    return is_within
