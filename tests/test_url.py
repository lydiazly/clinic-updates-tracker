# -*- coding: utf-8 -*-
# tests/test_url.py
# pytest tests/test_url.py --browser-channel chromium
from playwright.sync_api import Page, expect
import pytest

from clinictracker.config import TARGET_BASE_URL
from clinictracker.startup import get_full_url


BASE_URL = "https://base_url"


@pytest.mark.parametrize(
    "sub, sub_url_expected",
    [
        ({'arg1': 'foo bar'}, "?arg1=foo+bar"),
        ({'arg1': 'val1', 'arg2': 'val2'}, "?arg1=val1&arg2=val2"),
        ("sub_path", "/sub_path"),
        ("sub_path", "/sub_path"),
    ],
)
def test_get_full_url(sub, sub_url_expected):
    """Tests startup.get_full_url()."""
    assert get_full_url(BASE_URL, sub) == BASE_URL + sub_url_expected


@pytest.mark.parametrize(
    "query, text_expected",
    [({'list_town': 'Dummy'}, "Updates regarding %s")],
)
def test_url(page: Page, query, text_expected):
    """Tests TARGET_BASE_URL."""
    city: str = query.get('list_town', '')
    page.goto(get_full_url(TARGET_BASE_URL, query))
    # Expects an element to match the text
    expect(
        page.locator(f'strong:has-text("{text_expected % city}")')
    ).to_be_visible()
