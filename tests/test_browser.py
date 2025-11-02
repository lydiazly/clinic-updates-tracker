# -*- coding: utf-8 -*-
# tests/test_browser.py
import logging
import platform
import pytest

from clinictracker.config import Config, TARGET_BASE_URL
from clinictracker.startup import QueryParams, get_full_url
from clinictracker.core import run, TEST_MSG, BROWSER_CLOSED_MSG


@pytest.mark.asyncio
async def test_chromium(caplog):
    """Tests launching chromium (new headless mode)."""
    headless_shell = platform.system() == 'Linux'
    config = Config(
        debug=False,
        test=True,
        headed_mode=False,
        browser_name='chromium',
        headless_shell=headless_shell,
    )
    query_dict = {'only_accepting': 'yes', 'list_town': 'Dummy'}
    full_url = get_full_url(TARGET_BASE_URL, query_dict)
    query = QueryParams(
        url=full_url,
        city='Dummy',
        days_back=2,
        nmax=10,
        tz='',
    )

    with caplog.at_level(logging.INFO):
        res = await run(query, config)
        # Assert returns None
        assert res is None
        # Check the log records more specifically
        assert len(caplog.records) >= 2
        assert caplog.records[-2].message == TEST_MSG
        assert caplog.records[-1].message == BROWSER_CLOSED_MSG
