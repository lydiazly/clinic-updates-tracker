# -*- coding: utf-8 -*-
# tests/test_selector.py
# pytest tests/test_selector.py --browser-channel chromium -s
import os
from playwright.sync_api import Page, expect
from src.clinic_updates_tracker.selectors import TITLE_SELECTOR, UPDATES_CONTAINER_SELECTOR, UPDATES_TITLE_SELECTOR, \
    UPDATES_LIST_SELECTOR, UPDATES_ITEM_SELECTOR, UPDATES_EMPTY_SELECTOR


def test_selectors_from_file(page: Page):
    """Tests selectors."""
    timeout = 500

    # Load HTML file
    html_file_path = os.path.abspath("./tests/sample.html")
    page.goto(f"file://{html_file_path}")

    # Test specific selector
    container = page.locator(UPDATES_CONTAINER_SELECTOR)
    expect(container, "Container not found").to_be_visible(timeout=timeout)
    print(f"\nTitle: {container.locator(TITLE_SELECTOR).inner_text()}")

    title = container.locator(UPDATES_TITLE_SELECTOR)
    expect(title, "list title not found").to_be_visible(timeout=timeout)
    print(f"List title: {title.inner_text()}")

    list = container.locator(UPDATES_LIST_SELECTOR).first
    expect(list, "List not found by `.first`").to_be_visible(timeout=timeout)

    list = container.locator(UPDATES_LIST_SELECTOR).locator('nth=0')
    expect(list, "List not found by `.locator('nth=0')`").to_be_visible(timeout=timeout)

    items = list.locator(UPDATES_ITEM_SELECTOR)
    expect(items.first, "Item not found").to_be_visible(timeout=timeout)
    print(f"{items.count()} items found:")
    for item in items.all():
        print(item.get_by_role("link").inner_text())
        print(item.get_by_role("link").get_attribute("href"))

    list2 = container.locator(UPDATES_LIST_SELECTOR + 'not').locator('nth=0')
    expect(list2, "List found but should not be").not_to_be_visible(timeout=timeout)

    text = container.locator(UPDATES_EMPTY_SELECTOR)
    expect(text, "Text not found.").to_be_visible(timeout=timeout)
    print(f"Text: {text.inner_text()}")
