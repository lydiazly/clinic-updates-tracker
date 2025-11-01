# -*- coding: utf-8 -*-
# tests/test_page.py
import logging
import platform
import pytest

from clinictracker.models import ListData
from clinictracker.config import RunConfig, TARGET_BASE_URL, OUTPUT_HTML_PATH
from clinictracker.startup import QueryParams, get_full_url
from clinictracker.core import run, BROWSER_CLOSED_MSG
from clinictracker.selectors import (
    LIST_TITLE_PREFIX,
    TITLE_PREFIX,
    EMPTY_SIGN_PREFIX,
)


@pytest.mark.asyncio
async def test_page(caplog):
    """Tests loading result page (chromium new headless mode)."""
    city = 'Dummy'
    headless_shell = platform.system() == 'Linux'
    config = RunConfig(
        debug=False,
        test=False,
        headed_mode=False,
        browser_name='chromium',
        headless_shell=headless_shell,
        export=False,
        output_path=OUTPUT_HTML_PATH,
        to_stdout=False,
    )
    query_dict = {'only_accepting': 'yes', 'list_town': city}
    full_url = get_full_url(TARGET_BASE_URL, '?', query_dict)
    query = QueryParams(
        url=full_url,
        city=city,
        days_back=2,
        nmax=10,
        tz='',
    )

    with caplog.at_level(logging.DEBUG):
        res_all = await run([query], config)
        # Assert returns ListData
        for res in res_all:
            assert isinstance(res, ListData)
        # Check the log records more specifically
        assert len(caplog.records) >= 6
        # assert "Using selector" in caplog.records[0].message
        assert "Options: {'headless':" in caplog.records[0].message
        assert full_url in caplog.records[1].message
        assert f"{TITLE_PREFIX} {city}" in caplog.records[2].message
        assert f"{LIST_TITLE_PREFIX} {city}" in caplog.records[3].message
        assert EMPTY_SIGN_PREFIX in caplog.records[4].message
        assert caplog.records[-1].message == BROWSER_CLOSED_MSG
