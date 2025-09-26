# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/core.py
# python -c "from src.clinic_updates_tracker.__main__ import main; main()"
"""Use Playwright to find the updates."""
import argparse
import logging
import random
import re
from time import sleep, time
import traceback
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Locator, TimeoutError

# from . import LAST_RUN_AT_ABSOLUTE_PATH
from . import HTML_FILE_NAME
from .browsers import get_browser
from .selectors import TITLE_SELECTOR, UPDATES_CONTAINER_SELECTOR, UPDATES_TITLE_SELECTOR, \
    UPDATE_LIST_SELECTOR, UPDATES_ITEM_SELECTOR, UPDATES_EMPTY_SELECTOR, \
    DETAIL_TITLE_SELECTOR, DETAIL_DATE_SELECTOR, DETAIL_CONTENT_SELECTOR
from .helpers import clear_content, is_date_within_n_days


# Global variables
TIMEOUT = 30000  # milliseconds
TIMEOUT_UL = 3000  # milliseconds


def close_everything(browser: Browser, context: BrowserContext) -> str:
    """Gracefully close everything."""
    try:
        context.close()
        browser.close()
        return "Closed gracefully."
    except Exception:
        return ''


def navigate_to_page(page: Page, url: str) -> tuple[bool, str]:
    """Navigate to the page and returns a tuple of status and message."""
    try:
        page.goto(url)
        page.wait_for_load_state("networkidle")
    except TimeoutError:
        return False, f"Timed out after {TIMEOUT/1000:g} s."
    except Exception as e:
        return False, e
    else:
        return True, ''


def get_update_list(page: Page, url: str, n_days: int, nmax: int, logger: logging.Logger) -> tuple[bool, str, list[dict] | None]:
    """Navigates to the page and finds the update list."""
    success, msg = navigate_to_page(page, url)
    if not success:
        return success, f"Unable to load {url}: {msg}", None
    logger.info(f"Result page loaded: {url}")

    # Find the <strong>Updates regarding...</strong> element,
    # then navigate to following sibling <ul>
    container_locator = page.locator(UPDATES_CONTAINER_SELECTOR)
    list_title_locator = container_locator.locator(UPDATES_TITLE_SELECTOR)
    list_locator = container_locator.locator(UPDATE_LIST_SELECTOR).locator("nth=0")  # .first
    no_updates_text_locator = container_locator.locator(UPDATES_EMPTY_SELECTOR)

    # Wait for the container to be loaded
    try:
        container_locator.wait_for(state="visible")
        logger.info(f"Result title: {container_locator.locator(TITLE_SELECTOR).inner_text().strip()}")
    except TimeoutError:
        return False, f"Timeout waiting for '{UPDATES_CONTAINER_SELECTOR}' after {TIMEOUT/1000:g} s.", None

    # Wait for the updates title to be loaded
    try:
        list_title_locator.wait_for(state="visible")
        logger.info(f"List title: {list_title_locator.inner_text().strip()}")
    except TimeoutError:
        return False, f"Timeout waiting for '{UPDATES_TITLE_SELECTOR}' after {TIMEOUT/1000:g} s.", None

    # Wait for the list to be loaded
    try:
        list_locator.wait_for(state="visible", timeout=TIMEOUT_UL)
        items_locator = list_locator.locator(UPDATES_ITEM_SELECTOR)
        # If at least one <li> is loaded
        items_locator.locator("nth=0").wait_for(state="visible", timeout=TIMEOUT_UL)
        logger.info(f"List loaded. {items_locator.count()} updates found.")
    except TimeoutError:
        try:
            no_updates_text_locator.wait_for(state="visible", timeout=TIMEOUT_UL)
            return True, "No updates found: " + no_updates_text_locator.inner_text().strip(), []
        except TimeoutError:
            return False, f"Timeout waiting for updates after {TIMEOUT/1000:g} s.", None

    # Get items
    item_locator_list = items_locator.all()
    item_list = []
    count = 0
    current_time = time()
    logger.info(f"Checking updates in the past {n_days} days (collect first {nmax} items)...")

    for item_locator in item_locator_list:
        if count >= nmax:
            break

        success, msg, res = parse_item(page, item_locator, logger)
        if not success:
            return success, msg, None

        if res:
            # If within n days, append to the list
            if res['date']:
                success, msg, is_within = is_date_within_n_days(res['date'], current_time, n_days)
                if success:
                    if is_within:
                        item_list.append(res)
                        # logger.info(msg)
                        count += 1
                    else:
                        # logger.info(msg)
                        break
                else:
                    logger.error(msg)
            # If no date found, set to 'Unknown' and append to the list
            else:
                res['date'] = 'Unknown'
                item_list.append(res)

        sleep(random.uniform(1, 3))  # pause for a random interval

    return success, f"{len(item_list)} updates collected.", item_list


def parse_item(page: Page, item: Locator, logger: logging.Logger) -> tuple[bool, str, dict]:
    """Parses the page (and detail page) and retrieves the title, URL, date, and content, of this item."""
    # Get info from result page
    link = item.get_by_role("link")
    match = re.search(r"\(\s*[Pp]osted\s+([^\)]*)\s*\)", item.inner_text())  # Search for '(Posted {date})'
    info = {
        'title': link.inner_text().strip(),
        'url': link.get_attribute("href"),
        'date': '' if match is None else match.group(1),
    }

    # Get info and content from the detail page in a new tab
    success, msg, info_from_detail, content = get_details(page, info['url'], logger)
    # Update info
    if info_from_detail is not None:
        if info_from_detail['title'] and info_from_detail['title'] != info['title']:
            info['title'] = info_from_detail['title']
        if info_from_detail['date'] and info_from_detail['date'] != info['date']:
            info['date'] = info_from_detail['date']

    return success, msg, info | {'content': content}


def get_details(page: Page, url: str, logger: logging.Logger) -> tuple[bool, str, str | None, str]:
    """Retrieves title, date, and content, on detail page."""
    # Get the current context to create a new page (tab)
    context = page.context
    # Create a new page (tab)
    new_page = context.new_page()
    success, msg = navigate_to_page(new_page, url)
    if not success:
        new_page.close()
        return success, f"Unable to load {url} in a new tab: {msg}", None, ''
    # logger.info(f"Detail page loaded in a new tab: {url}")

    info = {'title': '', 'date': ''}
    title_locator = new_page.locator(DETAIL_TITLE_SELECTOR)
    date_locator = new_page.locator(DETAIL_DATE_SELECTOR)
    content_locator = new_page.locator(DETAIL_CONTENT_SELECTOR)
    content = clear_content(content_locator.inner_html())
    info['title'] = title_locator.inner_text().strip()
    info['date'] = date_locator.inner_text().strip()

    new_page.close()
    return success, msg, info, content


def construct_content(item_list: list[dict], city: str, n_days: int, nmax: int) -> list[str]:
    """Constructs HTML content as lines."""
    if len(item_list) == 0:
        return []

    lines = [f"<h2>Updates regarding {city} in the past {n_days} days</h2>"]
    lines.append(f"<p><strong>First {nmax} updates:</strong></p>")
    lines.append("<ol>")
    for item in item_list:
        lines.append(
            "<li><strong>"
            + f"<a href=\"{item['url']}\">{item['title']}</a>"
            + f" (Posted {item['date']})"
            + "</strong></li>"
        )
        lines.append(item['content'])
    lines.append("</ol>")
    return lines


# Main functionality
def run(
    args: argparse.Namespace,
    logger: logging.Logger = logging.getLogger(),
    target_url: str = "",
) -> bool:
    with sync_playwright() as p:
        browser = get_browser(p, args, logger)
        if browser is None:
            return False

        context = browser.new_context()  # incognito
        page = context.new_page()
        context.set_default_timeout(TIMEOUT)

        try:
            if args.test:
                logger.info("*** Test only (no operation) ***")
                return True

            # Directly go to the search result page -------------------|
            success, msg, item_list = get_update_list(page, target_url, args.days, args.nmax, logger)
            if success:
                logger.info(msg)
            else:
                logger.error(msg)
                return False

            # Print to stdout (for testing)
            # logger.info(f"Showing first {args.nmax} updates:")
            # for i, item in enumerate(item_list):
            #     print(f"{i + 1}.")
            #     print(f"[Title] {item['title']}")
            #     print(f"[Date] {item['date']}")
            #     print(f"[URL] {item['url']}")
            #     print(f"[Content]\n{item['content']}\n")

            # Save part of the HTML to a file (for GitHub Actions)
            lines = construct_content(item_list, args.city, args.days, args.nmax)
            content = '\n'.join(lines)
            with open(HTML_FILE_NAME, "w") as f:
                f.write(content)
            logger.info(f"Saved to '{HTML_FILE_NAME}'." + (" (empty)" if len(lines) == 0 else ''))

            # Save complete HTML to a file (for testing)
            # lines = ["<!DOCTYPE html>", "<html>", "<body>"] + lines + ["</body>", "</html>"]
            # content = '\n'.join(lines)
            # with open("tmp_" + HTML_FILE_NAME, "w") as f:
            #     f.write(content)

        except Exception:
            traceback.print_exc()
            return False

        else:
            return True

        finally:
            # Close
            logger.info(close_everything(browser, context))
