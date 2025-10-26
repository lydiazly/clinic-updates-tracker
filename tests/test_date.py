# -*- coding: utf-8 -*-
# tests/test_date.py
# pytest tests/test_url.py -s
from datetime import datetime
from dateutil.parser import parse, ParserError
import pytest
from time import time

from clinictracker.utils import is_date_within


@pytest.mark.parametrize(
    "datetime_str, expected_datetime",
    [
        ("2025-09-01", datetime(2025, 9, 1)),
        ("September 1, 2025", datetime(2025, 9, 1)),
        ("Sep 1, 2025", datetime(2025, 9, 1)),
        ("1 Sep 2025", datetime(2025, 9, 1)),
        ("1st Sep 2025", datetime(2025, 9, 1)),
        ("9/1/2025", datetime(2025, 9, 1)),
        ("9.1.2025", datetime(2025, 9, 1)),
        ("September 1, 2025 12:00 PM", datetime(2025, 9, 1, 12, 0)),
        ("September 1, 2025 12:00 AM", datetime(2025, 9, 1, 0, 0)),
        ("September 1, 2025 0:00 AM", datetime(2025, 9, 1, 0, 0)),
    ],
)
def test_parse_datetime(datetime_str, expected_datetime):
    """Tests parsing strings."""
    assert parse(datetime_str) == expected_datetime


@pytest.mark.parametrize(
    "target_date, days_back, ref_datetime, tz",
    [
        ("September 1, 2025", 1, parse("2025-09-02T13:00Z"), ''),
        ("September 1, 2025", 1, parse("2025-09-02T13:00Z"), 'UTC'),
        ("September 1, 2025", 1, parse("2025-09-02 13:00 PDT"), ''),
        ("September 1, 2025 0:00 AM", 1, parse("2025-09-02T01:00Z"), ''),
        ("2025-09-01T00:00Z", 1, parse("2025-09-02T01:00Z"), ''),
        ("Sep 1, 2025", 1, parse("2025-09-02T13:00"), 'America/Vancouver'),
        ("Sep 1, 2025", 1, parse("2025-09-02T20:00Z"), 'America/Vancouver'),
        ("December 31, 2024", 1, parse("2025-01-01T13:00Z"), ''),
    ],
)
def test_date_within(target_date, days_back, ref_datetime, tz):
    """Tests dates within the time range."""
    res = is_date_within(target_date, days_back, ref_datetime, tz)
    assert res.data
    # print('\n' + res.messages[0])


@pytest.mark.parametrize(
    "target_date, days_back, ref_datetime, tz",
    [
        ("September 1, 2025", 1, parse("2025-09-02T13:01Z"), ''),
        ("September 1, 2025", 1, parse("2025-09-02 13:01 PDT"), ''),
        ("September 1, 2025 0:00 AM", 1, parse("2025-09-02T01:01Z"), ''),
        ("Sep 1, 2025", 1, parse("2025-09-02T13:01"), 'America/Vancouver'),
        ("Sep 1, 2025", 1, parse("2025-09-02T20:01Z"), 'America/Vancouver'),
        ("December 31, 2024", 1, parse("2025-01-01T13:01Z"), ''),
    ],
)
def test_date_not_within(target_date, days_back, ref_datetime, tz):
    """Tests dates not within the time range."""
    res = is_date_within(target_date, days_back, ref_datetime, tz)
    assert not res.data
    # print('\n' + res.messages[0])


tz_warning = "Applying local time zone to the target time."


@pytest.mark.parametrize(
    "target_date, ref_datetime, tz, warning",
    [
        (
            "September 1, 2025",
            parse("2025-09-02T13:00"),
            'nowhere',
            f"Time zone not found: nowhere\n{tz_warning}",
        ),
        ("September 1, 2025", parse("2025-09-02T13:00"), '', tz_warning),
    ],
)
def test_warnings(target_date, ref_datetime, tz, warning):
    """Tests warnings."""
    res = is_date_within(target_date, 1, ref_datetime, tz)
    assert res.data
    assert warning == '\n'.join(res.warnings)
    # print('\n' + '\n'.join(res.warnings))


@pytest.mark.parametrize(
    "invalid_date, error_msg",
    [
        ("", r"^\(is_date_within\) Target date is missing.$"),
        (None, r"^\(is_date_within\) Target date is missing.$"),
        (
            time(),
            (
                r"^\(is_date_within\) Error parsing date:\n"
                r"Target date must be a string, datetime, or date object.$"
            ),
        ),
        ("not a date", r"^\(is_date_within\) Error parsing date:"),
    ],
)
def test_date_invalid(invalid_date, error_msg):
    """Tests invalid inputs."""
    with pytest.raises((ParserError, ValueError), match=error_msg):
        is_date_within(invalid_date, 1)
