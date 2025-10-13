# -*- coding: utf-8 -*-
# utils.py
"""Generic utility functions."""
from bs4 import BeautifulSoup
from bs4.element import Tag, PageElement
from datetime import datetime, timezone, date, tzinfo
from dateutil.parser import parse, ParserError
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from clinictracker.startup import QueryParams
from clinictracker.models import Result, ListData

TITLE_TEMPLATE = "%(city)s clinic updates in the past %(days_back)s days"


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
    cleared_content = "\n".join(
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
    remove_list = ["Clinic Website", "Contact Information & Map", "Contact"]
    soup = BeautifulSoup(html_content, 'html.parser')
    # Find all <a> tags and remove if matches any of remove_list
    for tag in soup.find_all('a'):
        if tag.string and tag.string.strip() in remove_list:
            tag.decompose()
    text = soup.get_text('\n', strip=True)
    return text


def construct_content(list_data: ListData, query: QueryParams) -> str:
    """Constructs HTML content and concatenates into a string."""
    if len(list_data.item_list) == 0:
        return ''

    title = TITLE_TEMPLATE % query._asdict()
    lines = [f"<h2>{title}</h2>"]
    lines.append("<ol>")
    for item in list_data.item_list:
        lines.append(
            "<li><strong>"
            f'<a href="{item.url}">{item.title}</a>'
            f" (Posted {item.date})"
            "</strong></li>"
        )
        if item.content:
            lines.append(item.content)
    if len(list_data.item_list) < list_data.n_tot:
        lines.append(
            f'<p><a href="{query.url}">'
            "<em>Go to website to view full list</em>"
            "</a></p>"
        )
    lines.append("</ol>")
    lines = (
        ["<!DOCTYPE html>", "<html>", "<head>"]
        + ['<meta charset="utf-8">', f"<title>{title}</title>"]
        + ["</head>", "<body>"]
        + lines
        + ["</body>", "</html>"]
    )
    return '\n'.join(lines)


def print_content(list_data: ListData, query: QueryParams) -> None:
    """Prints content as plain text to STDOUT."""
    if len(list_data.item_list) > 0:
        print("\n" + TITLE_TEMPLATE % query._asdict() + ":\n")
        for i, item in enumerate(list_data.item_list):
            print(f"{i + 1}.")
            if item.url:
                print(f"{item.url}")
            print(f"{item.title}")
            print(f"(Date: {item.date})")
            if item.content:
                print(html_to_plain(item.content))
            print('')
        if len(list_data.item_list) < list_data.n_tot:
            print(f"--> Go to website to view full list:\n{query.url}\n")
    else:
        print("Nothing to print.")


def is_date_within_n_days(
    date_str: str,
    days_back: int,
    tz: str = '',
) -> Result[bool]:
    """Checks if a given date is within the past n days.

    Args:
        date_str (str): the date to be checked, assuming at noon
                        (any format, no time zone needed)
        days_back (int): number of days up to now
        tz (str): time zone of the date_str

    Returns:
        Result: A namedtuple with fields:
            data (bool): Is within the past n days or not
            messages (list[str])
            warnings (list[str])

    Raises:
        ValueError: If the date string is empty or unable to be parsed
    """
    if not date_str.strip():
        raise ValueError("Date string is empty.")

    # Preset time (adjust this if needed)
    ref_time_str: str = ' 12:00:00'

    # Get current time (naive)
    now_naive: datetime = datetime.now()
    # Presumed to be in the system's local time zone
    now_local: datetime = now_naive.astimezone()
    # now_local_str: str = now_local.strftime('%B %d, %Y (%Z)')

    # Get current time in UTC (for logging only)
    now_utc: datetime = datetime.now(timezone.utc)  # timezone-aware
    now_date_utc: date = now_utc.date()
    now_utc_str: str = now_date_utc.strftime('%Y-%m-%d (UTC)')
    # now_str_all: str = f"{now_local_str} / {now_utc_str}"

    messages: list[str] = []
    warnings: list[str] = []
    tz_info: ZoneInfo | tzinfo | None = None
    tzname: str
    now_target: datetime
    # Use provided TZ identifier/name
    if tz:
        try:
            tz_info = ZoneInfo(tz.strip())  # <class 'zoneinfo.ZoneInfo'>
            tzname = tz_info.key  # or str(tz_info)
        except ZoneInfoNotFoundError as e:
            # Set now_target later
            warnings.append(f"{e}. System's local time zone used.")
        else:
            # Convert to target timezone
            now_target = now_local.astimezone(tz_info)

    # Or use the system's local time zone
    if tz_info is None:
        tz_info = now_local.tzinfo  # <class 'datetime.timezone'>
        tzname = str(tz_info)
        now_target = now_local

    now_date_target: date = now_target.date()
    now_target_str: str = now_target.strftime('%B %d, %Y (%Z)')
    # Note: '%Z' may be different from the TZ name
    now_str_all: str = f"{now_target_str} / {now_utc_str}"

    is_within: bool = False
    try:
        # Parse the string (just date) using dateutil.parser.parse with tz
        parsed_datetime: datetime = parse(
            date_str + ref_time_str,
            default=datetime.now(tz_info),
        )  # timezone-aware
        parsed_date: date = parsed_datetime.date()

    except (ParserError, TypeError) as e:
        raise ParserError(f"Error parsing date string: {e}")

    else:
        # Convert to UTC (for logging only)
        parsed_date_utc: date = parsed_datetime.astimezone(timezone.utc).date()
        date_utc_str: str = parsed_date_utc.strftime('%Y-%m-%d (UTC)')
        date_str_with_tz: str = f"{date_str} ({tzname})"
        date_str_all: str = f"{date_str_with_tz} / {date_utc_str}"

        # Compare the date
        # days_diff: int = (now_date_utc - parsed_date_utc).days
        days_diff: int = (now_date_target - parsed_date).days
        is_within = days_diff <= days_back
        # Note: days_diff might be less than 0 since the time is preset

        if is_within:
            messages.append(
                f"{date_str_all} is within {days_back} days before "
                f"{now_str_all}. Collecting..."
            )
        else:
            messages.append(
                f"{date_str_all} is {days_diff} "
                f"day{'s' if days_diff > 1 else ''} earlier than "
                f"{now_str_all}. Returning..."
            )

        return Result(
            data=is_within,
            messages=messages,
            warnings=warnings,
        )
