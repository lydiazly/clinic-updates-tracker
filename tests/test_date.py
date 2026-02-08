# -*- coding: utf-8 -*-
# tests/test_date.py
# pytest tests/test_url.py -s
from datetime import datetime, timedelta
from dateutil.parser import parse, ParserError
import logging
import pytest
from time import time

from clinictracker.utils import is_date_within, pretty_time_delta


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
    "timedelta, expected_str",
    [
        (timedelta(seconds=86400), "1d00h00m00s"),
        (timedelta(seconds=-86400), "-1d00h00m00s"),
        (timedelta(seconds=3723.5), "01h02m03s"),
        (timedelta(days=-1, hours=-2, minutes=-3, seconds=-4), "-1d02h03m04s"),
    ],
)
def test_print_timedelta(timedelta, expected_str):
    """Tests parsing strings."""
    assert pretty_time_delta(timedelta) == expected_str


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
    is_within = is_date_within(target_date, days_back, ref_datetime, tz)
    assert is_within
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
    is_within = is_date_within(target_date, days_back, ref_datetime, tz)
    assert not is_within
    # print('\n' + res.messages[0])


USE_LOCAL_TZ_MSG = "Applying local time zone to the target time."
TZ_NOT_FOUND_MSG = "Time zone not found: %s"


@pytest.mark.parametrize(
    "target_date, ref_datetime, tz, warning",
    [
        (
            "September 1, 2025",
            parse("2025-09-02T13:00"),
            'nowhere',
            '\n'.join([TZ_NOT_FOUND_MSG % 'nowhere', USE_LOCAL_TZ_MSG]),
        ),
        ("September 1, 2025", parse("2025-09-02T13:00"), '', USE_LOCAL_TZ_MSG),
    ],
)
def test_warnings(caplog, target_date, ref_datetime, tz, warning):
    """Tests warnings."""
    with caplog.at_level(logging.INFO):
        is_within = is_date_within(target_date, 1, ref_datetime, tz)
        assert is_within
        assert all(r.levelno == logging.WARNING for r in caplog.records)
        assert '\n'.join(r.message for r in caplog.records) == warning
        # print('\n' + '\n'.join(r.message for r in caplog.records))


DATE_ERR = r"^\(is_date_within\) Error parsing date:"
NO_DATE_ERR = r"^\(is_date_within\) Target date is missing.$"
INVALID_DATE_ERR = r"Target date must be a string, datetime, or date object.$"


@pytest.mark.parametrize(
    "invalid_date, error_msg",
    [
        ("", NO_DATE_ERR),
        (None, NO_DATE_ERR),
        (time(), '\n'.join([DATE_ERR, INVALID_DATE_ERR])),
        ("not a date", DATE_ERR),
    ],
)
def test_date_invalid(invalid_date, error_msg):
    """Tests invalid inputs."""
    with pytest.raises((ParserError, ValueError), match=error_msg):
        is_date_within(invalid_date, 1)
