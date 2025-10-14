# -*- coding: utf-8 -*-
# tests/conftest.py
import platform
import pytest


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    if platform.system() == 'Linux':
        browser_type_launch_args.pop("channel", None)
        return {
            **browser_type_launch_args,
            'headless': True,
        }
    else:
        return {
            **browser_type_launch_args,
            'channel': 'chromium',
        }
