# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/helpers.py
from bs4 import BeautifulSoup, Tag, NavigableString
import argparse
import logging
import re
import sys
from urllib.parse import urlencode

from . import target_base_url, default_city, browser_choices


def get_full_url(base_url: str, delim: str = '?', sub: dict|str = {}) -> str:
    """Appends `sub` (a query dict or a subdirectory string) to the base URL:
    {base_url}?arg1=val1&... or {base_url}/..."""
    if delim == '?' and isinstance(sub, dict):  # query
        full_url = f"{base_url}?{urlencode(sub)}"  # will encode special characters as well
    else:  # subdirectory
        full_url = f"{base_url}/{str(sub)}"
    return full_url


def setup_logger(name: str = '') -> logging.Logger:
    """Sets and returns the logger."""
    if name:
        # Level=INFO, use a local logger with a name
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
        # Suppress urllib3 warnings
        logging.getLogger("urllib3").setLevel(logging.ERROR)
    else:
        # Level=DEBUG, use the root logger
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelno)s - %(message)s")
        logger = logging.getLogger()
    return logger


def get_options() -> tuple[argparse.Namespace, logging.Logger]:
    """Gets options from user and sets the logger."""

    parser = argparse.ArgumentParser(
        description=f"Check updates on {target_base_url}"
    )
    parser.add_argument(
        "city", type=str, nargs="?", default=default_city, help="town/city (default: %(default)s)"
    )
    parser.add_argument(
        "-a", "--all", action="store_true", help="all updates (only affects the clinic table but not the update list)"
    )
    parser.add_argument(
        "-H", "--headed", action="store_true", help="run in headed mode (default: headless)"
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="print debug logs"
    )
    parser.add_argument(
        "-b", "--browser",
        choices=browser_choices,
        default="chromium",
        metavar="<browser>",
        help=f"choose a browser: {', '.join(browser_choices)} (default: %(default)s)"
    )
    parser.add_argument(
        "--headless-shell",
        dest="shell",
        action="store_true",
        help="use a separate headless shell for chromium headless mode"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="test the browser without any page operation"
    )
    args = parser.parse_args()

    # Append a subdirectory or query
    # {target_base_url}?... or {target_base_url}/...
    target_url = (target_base_url + "?"
                + ("" if args.all else "only_accepting=yes&")
                + "list_town=" + args.city
    )
    # Note: 'only_accepting' only affects the clinic table but not the update list
    query_dict = ({'only_accepting': 'yes'} if not args.all else {}) | {'list_town': args.city}
    target_url = get_full_url(target_base_url, '?', query_dict)

    logger = setup_logger('' if args.debug else __name__)

    return args, logger, target_url


def preserve_tags(element) -> str:
    """Extracts the textual content of an HTML element while preserving certain tags."""
    if element.name in ['br', 'p', 'i', 'b', 'a', 'em']:
        text = str(element)
    else:
        text = element.get_text()
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return text


def remove_node(node):
    """Removes either a NavigableString or a Tag."""
    if isinstance(node, NavigableString):
        node.extract()  # remove text node
    elif isinstance(node, Tag):
        node.decompose()  # remove HTML tag


def extract_detail_content(content: str) -> tuple[str, str, str]:
    """Clears content."""
    soup = BeautifulSoup(content, 'html.parser')

    cleared_content = " ".join(map(preserve_tags, soup))
    cleared_content = re.sub(r"(<p>\s*</p>)+", "", cleared_content)  # remove any '<p></p>'
    cleared_content = re.sub(r"\s*<p>\s*|\s*</p>\s*", "<br />", cleared_content)  # '<p>...</p>' --> '<br />...<br />'
    cleared_content = re.sub(r"(\s*<br\s*/?>\s*)+", "<br />", cleared_content)  # multiple <br /> --> <br />
    cleared_content = re.sub(r'^<br />|<br />$', '', cleared_content)  # remove leading and trailing <br/>

    return cleared_content
