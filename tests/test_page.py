# -*- coding: utf-8 -*-
# tests/test_page.py
# pytest tests/test_page.py --browser-channel chromium
import logging

from clinictracker.config import Config, TARGET_BASE_URL, OUTPUT_HTML_PATH
from clinictracker.startup import QueryParams, get_full_url
from clinictracker.core import run, CLOSED_MSG
from clinictracker.selectors import (
    LIST_TITLE_PREFIX,
    TITLE_PREFIX,
    EMPTY_CUE_PREFIX,
)


def test_page(caplog):
    """Tests loading result page (chromium new headless mode)."""
    city = 'Dummy'
    config = Config(
        debug=False,
        test=False,
        headed_mode=False,
        browser_name='chromium',
        headless_shell=False,
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

    with caplog.at_level(logging.INFO):
        res = run(query, config)
        # Assert returns None
        assert res is None
        # Check the log records more specifically
        assert len(caplog.records) >= 5
        assert full_url in caplog.records[0].message
        assert f"{TITLE_PREFIX} {city}" in caplog.records[1].message
        assert f"{LIST_TITLE_PREFIX} {city}" in caplog.records[2].message
        assert EMPTY_CUE_PREFIX in caplog.records[3].message
        assert caplog.records[-1].message == CLOSED_MSG
