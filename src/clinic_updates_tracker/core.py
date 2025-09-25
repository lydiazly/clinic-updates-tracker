# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/core.py
# python -c "from src.clinic_updates_tracker.__main__ import main; main()"
"""Use Playwright to find the updates."""
import traceback
import logging
import argparse
import re
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Locator, TimeoutError

from .browsers import get_browser
from .selectors import TITLE_SELECTOR, UPDATES_CONTAINER_SELECTOR, UPDATES_TITLE_SELECTOR, \
    UPDATES_LIST_SELECTOR, UPDATES_ITEM_SELECTOR, UPDATES_EMPTY_SELECTOR

# Global variables
TIMEOUT = 30000  # milliseconds
TIMEOUT_UL = 1000  # milliseconds


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
    except TimeoutError:
        return False, f"Timed out after {TIMEOUT/1000:g} s."
    except Exception as e:
        return False, e
    else:
        return True, ''


#TODO
def get_update_list(page: Page, url: str, logger: logging.Logger) -> tuple[bool, str, list[Locator] | None]:
    """Navigates to the page and finds the updates list."""
    success, msg = navigate_to_page(page, url)
    if not success:
        return success, f"Unable to load {url}: {msg}", None
    logger.info(f"Page loaded: {url}")

    # Find the <strong>Updates regarding...</strong> element,
    # then navigate to following sibling <ul>
    container = page.locator(UPDATES_CONTAINER_SELECTOR)
    list_title = container.locator(UPDATES_TITLE_SELECTOR)
    list = container.locator(UPDATES_LIST_SELECTOR).locator("nth=0")  # .first
    no_updates_text = container.locator(UPDATES_EMPTY_SELECTOR)

    # Wait for the container to be loaded
    try:
        container.wait_for(state="visible")
        logger.info(f"Page title: {container.locator(TITLE_SELECTOR).inner_text().strip()}")
    except TimeoutError:
        return False, f"Timeout waiting for '{UPDATES_CONTAINER_SELECTOR}' after {TIMEOUT/1000:g} s.", None

    # Wait for the updates title to be loaded
    try:
        list_title.wait_for(state="visible")
        logger.info(f"List title: {list_title.inner_text().strip()}")
    except TimeoutError:
        return False, f"Timeout waiting for '{UPDATES_TITLE_SELECTOR}' after {TIMEOUT/1000:g} s.", None
    
    # Wait for the list to be loaded
    try:
        list.wait_for(state="visible", timeout=TIMEOUT_UL)
        items_locator = list.locator(UPDATES_ITEM_SELECTOR)
        # If at least one <li> is loaded
        items_locator.locator("nth=0").wait_for(state="visible", timeout=TIMEOUT_UL)
        logger.info(f"List loaded. {items_locator.count()} updates found.")
    except TimeoutError:
        try:
            no_updates_text.wait_for(state="visible", timeout=TIMEOUT_UL)
            return True, "No updates found: " + no_updates_text.inner_text().strip(), []
        except TimeoutError:
            return False, f"Timeout waiting for updates after {TIMEOUT/1000:g} s.", None

    # Wait for list items to be loaded
    items = items_locator.all()
    return True, "", items


#TODO
def parse_item(item: Locator) -> tuple[bool, str]:
    success, msg = True, ''
    link = item.get_by_role("link")
    url = link.get_attribute("href")
    title = link.inner_text().strip()
    match = re.search(r"\(\s*[Pp]osted\s+([^\)]*)\s*\)", item.inner_text())
    if match is None:
        #TODO
        # success, msg, date, text = parse_detail_page(url)
        date = ''
    else:
        date = match.group(1)
    print(url)
    print(title)
    print(date)
    return success, msg


#TODO
def parse_detail_page(url: str) -> tuple[bool, str, str, str]:
    return True, '', '', ''


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
            #TODO
            success, msg, items = get_update_list(page, target_url, logger)
            if not success:
                logger.error(msg)
                return False

            # TODO
            for i, item in enumerate(items):
                print(f"\n{i + 1}.")
                success, msg = parse_item(item)
                if not success:
                    logger.error(msg)
                    return False
            
            # if success:
            #     logger.info(msg)
            # else:
            #     logger.error(msg)
            #     return False

            # Save current time to 'last run time file', so we can check if we need to run this again
            # TODO(keep)
            # with open(last_run_at_absolute_path, "w") as f:
            #     f.write(str(time()))

        except Exception:
            traceback.print_exc()
            return False

        else:
            return True

        finally:
            # Close
            logger.info(close_everything(browser, context))
