# -*- coding: utf-8 -*-
# tests/test_page.py
import logging
import platform
import pytest

from clinictracker.models import ListData
from clinictracker.config import RunConfig, TARGET_BASE_URL, OUTPUT_HTML_PATH
from clinictracker.startup import QueryParams, get_full_url
from clinictracker.core import (
    run,
    BROWSER_CLOSED_MSG,
    NO_EXPORT_MSG,
    TASK_START_MSG,
    TASK_TITLE,
    INVALID_CITY_MSG,
)
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
        extract_cities=False,
    )
    query_dict = {'only_accepting': 'yes', 'list_town': city}
    full_url = get_full_url(TARGET_BASE_URL, query_dict)
    query = QueryParams(
        url=full_url,
        city=city,
        days_back=2,
        nmax=10,
        tz='',
    )
    task_title = TASK_TITLE.format(id=1, city=city)

    with caplog.at_level(logging.DEBUG):
        data_all = await run([query], config)
        # Assert returns a list of ListData with no items
        assert (
            isinstance(data_all, list)
            and isinstance(data_all[0], ListData)
            and not data_all[0].items
            and data_all[0].n_tot == 0
        )
        # Check the log records more specifically
        assert len(caplog.records) >= 13
        assert "Options: {'headless':" in caplog.records[0].message
        assert caplog.records[1].message == TASK_START_MSG.format(
            start=1, end=1, total=1
        )
        assert INVALID_CITY_MSG.format(city=city) in caplog.records[3].message
        assert full_url in caplog.records[4].message
        assert EMPTY_SIGN_PREFIX in caplog.records[5].message
        assert task_title in caplog.records[7].message
        assert f"{TITLE_PREFIX} {city}" in caplog.records[9].message
        assert f"{LIST_TITLE_PREFIX} {city}" in caplog.records[10].message
        assert caplog.records[-3].message == NO_EXPORT_MSG
        assert caplog.records[-1].message == BROWSER_CLOSED_MSG
