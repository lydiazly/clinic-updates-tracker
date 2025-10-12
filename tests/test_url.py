# -*- coding: utf-8 -*-
# tests/test_url.py
# pytest tests/test_url.py --browser-channel chromium
import pytest
from playwright.sync_api import Page, expect
from clinictracker.config import TARGET_BASE_URL
from clinictracker.startup import get_full_url


@pytest.mark.parametrize(
    "full_url, full_url_expected",
    [
        [
            get_full_url("https://base_url", '?', {'arg1': 'val1'}),
            "https://base_url?arg1=val1",
        ],
        [
            get_full_url(
                "https://base_url", '?', {'arg1': 'val1', 'arg2': 'val2'}
            ),
            "https://base_url?arg1=val1&arg2=val2",
        ],
        [
            get_full_url("https://base_url", '/', "sub_path"),
            "https://base_url/sub_path",
        ],
        [
            get_full_url("https://base_url", '?', "sub_path"),
            "https://base_url/sub_path",
        ],
    ],
)
def test_get_full_url(full_url, full_url_expected):
    """Tests startup.get_full_url()."""
    assert full_url == full_url_expected


@pytest.mark.parametrize(
    "url, text_expected",
    [
        [
            get_full_url(TARGET_BASE_URL, '?', {'list_town': 'some_city'}),
            "Updates regarding some_city",
        ],
    ],
)
def test_url(page: Page, url, text_expected):
    """Tests TARGET_BASE_URL."""
    page.goto(url)
    # Expects an element to match the text
    expect(page.locator(f'strong:has-text("{text_expected}")')).to_be_visible()
