# -*- coding: utf-8 -*-
# tests/test_browser.py
# pytest tests/test_browser.py --browser-channel chromium
import logging

from clinictracker.config import Config, TARGET_BASE_URL, OUTPUT_HTML_PATH
from clinictracker.startup import QueryParams, get_full_url
from clinictracker.core import run, TEST_MSG, CLOSED_MSG


def test_chromium(caplog):
    """Tests launching chromium (new headless mode)."""
    config = Config(
        debug=False,
        test=True,
        headed_mode=False,
        browser_name='chromium',
        headless_shell=False,
        export=False,
        output_path=OUTPUT_HTML_PATH,
        to_stdout=False,
    )
    query_dict = {'only_accepting': 'yes', 'list_town': 'Dummy'}
    full_url = get_full_url(TARGET_BASE_URL, '?', query_dict)
    query = QueryParams(
        url=full_url,
        city='Dummy',
        days_back=2,
        nmax=10,
        tz='',
    )

    with caplog.at_level(logging.INFO):
        res = run(query, config)
        # Assert returns None
        assert res is None
        # Check the log records more specifically
        assert len(caplog.records) == 2
        assert caplog.records[0].message == TEST_MSG
        assert caplog.records[-1].message == CLOSED_MSG
