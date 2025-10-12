# -*- coding: utf-8 -*-
# config.py
"""Configuration and constants."""
from argparse import Namespace
from dotenv import load_dotenv
import os
from pathlib import Path
from typing import NamedTuple


load_dotenv()

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Timeout in milliseconds
TIMEOUT_PAGE = int(os.getenv('TIMEOUT_PAGE', 30000))  # for loading page
TIMEOUT_UL = int(os.getenv('TIMEOUT_UL', 3000))  # for loading list

# File to export
OUTPUT_HTML_NAME = os.getenv('OUTPUT_HTML_NAME', 'content.html')
# OUTPUT_HTML_PATH: str = os.getenv(
#     'OUTPUT_HTML_PATH', f'./output/{OUTPUT_HTML_NAME}'
# )
OUTPUT_HTML_PATH: Path = Path(
    os.getenv('OUTPUT_HTML_PATH', f'./output/{OUTPUT_HTML_NAME}')
)
# Append a filename if needed
if OUTPUT_HTML_PATH.is_dir():
    OUTPUT_HTML_PATH = OUTPUT_HTML_PATH / OUTPUT_HTML_NAME

# Target website
TARGET_BASE_URL: str = os.getenv('TARGET_BASE_URL', '')
TARGET_TZ: str = os.getenv('TARGET_TZ', '')
CITY: str = os.getenv('CITY', '')
DAYS_BACK: int = int(os.getenv('DAYS_BACK', 2))  # default: 2 days
MAX_ITEMS: int = int(os.getenv('MAX_ITEMS'), 10)  # default: 10 items

# Available browsers
BROWSER_CHOICES = ['chromium', 'firefox', 'webkit']

# Users JSON file to import
# INPUT_USERS_JSON_PATH: str = os.getenv(
#     'INPUT_USERS_JSON_PATH', './input/users.json'
# )
INPUT_USERS_JSON_PATH: Path = Path(
    os.getenv('INPUT_USERS_JSON_PATH', './input/users.json')
)


class Config(NamedTuple):
    """Application configuration.

    Args:
        debug (bool): Set the logging level to DEBUG
        test (bool): Exit after opening a page without any further operation
        quiet (bool): Suppress INFO level outputs
        headed_mode (bool): Headed mode
        browser_name (str): Browser name
        headless_shell (bool): Use a separate chromium headless shell
        export (bool): Export to a file
        output_path (Path): Path of output file
        to_stdout (bool): Print results as plain text to STDOUT
    """
    debug: bool
    test: bool
    quiet: bool
    headed_mode: bool
    browser_name: str
    headless_shell: bool
    export: bool
    output_path: Path
    to_stdout: bool


def load_config(args: Namespace) -> Config:
    """Loads configuration from args and environment."""
    output_path: Path = args.output
    # Append a filename if needed
    if output_path.is_dir():
        output_path = output_path / OUTPUT_HTML_NAME
    return Config(
        debug=args.debug or DEBUG_MODE,
        test=args.test,
        quiet=args.quiet,
        headed_mode=args.headed,
        browser_name=args.browser,
        headless_shell=args.shell,
        export=args.export,
        output_path=output_path,
        to_stdout=args.to_stdout,
    )
