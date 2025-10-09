# -*- coding: utf-8 -*-
# tests/test_selector.py
# pytest tests/test_selector.py --browser-channel chromium -s
import os
from playwright.sync_api import Page, expect
from clinic_updates_tracker.selectors import TITLE_SELECTOR, UPDATES_CONTAINER_SELECTOR, UPDATES_TITLE_SELECTOR, \
    UPDATE_LIST_SELECTOR, UPDATES_ITEM_SELECTOR, UPDATES_EMPTY_SELECTOR, \
    DETAIL_TITLE_SELECTOR, DETAIL_DATE_SELECTOR, DETAIL_CONTENT_SELECTOR
from clinic_updates_tracker.helpers import clear_content

timeout = 500


def test_selectors_from_file1(page: Page):
    """Tests selectors on result page."""
    # Load HTML file
    html_file_path = os.path.abspath("./tests/sample1.html")
    page.goto(f"file://{html_file_path}")

    # Test selectors
    container = page.locator(UPDATES_CONTAINER_SELECTOR)
    expect(container, "Container not found on result page").to_be_visible(timeout=timeout)
    print(f"\nTitle on result page: {container.locator(TITLE_SELECTOR).inner_text()}")

    title = container.locator(UPDATES_TITLE_SELECTOR)
    expect(title, "List title not found on result page").to_be_visible(timeout=timeout)
    print(f"List title on result page: {title.inner_text()}")

    list = container.locator(UPDATE_LIST_SELECTOR).first
    expect(list, "List not found by `.first` on result page").to_be_visible(timeout=timeout)

    list = container.locator(UPDATE_LIST_SELECTOR).locator('nth=0')
    expect(list, "List not found by `.locator('nth=0')` on result page").to_be_visible(timeout=timeout)

    items = list.locator(UPDATES_ITEM_SELECTOR)
    expect(items.first, "Item not found on result page").to_be_visible(timeout=timeout)
    print(f"{items.count()} items on result page:")
    for item in items.all():
        print(item.get_by_role("link").inner_text())
        print(item.get_by_role("link").get_attribute("href"))

    list2 = container.locator(UPDATE_LIST_SELECTOR + 'not').locator('nth=0')
    expect(list2, "List found on result page but should not be").not_to_be_visible(timeout=timeout)

    text = container.locator(UPDATES_EMPTY_SELECTOR)
    expect(text, "Text not found on result page").to_be_visible(timeout=timeout)
    print(f"Text on result page: {text.inner_text()}")


def test_selectors_from_file2(page: Page):
    """Tests selectors on detail page."""
    # Load HTML file
    html_file_path = os.path.abspath("./tests/sample2.html")
    page.goto(f"file://{html_file_path}")

    # Test selectors
    title = page.locator(DETAIL_TITLE_SELECTOR)
    expect(title, "Title not found on detail page").to_be_visible(timeout=timeout)
    print(f"\nTitle on detail page: {title.inner_text()}")

    date = page.locator(DETAIL_DATE_SELECTOR)
    expect(date, "Date not found on detail page").to_be_visible(timeout=timeout)
    print(f"Date on detail page: {date.inner_text()}")

    content = page.locator(DETAIL_CONTENT_SELECTOR)
    expect(content, "Content not found on detail page").to_be_visible(timeout=timeout)
    # print("Content:")
    # print(content.inner_html())
    print("Cleared content:")
    print(clear_content(content.inner_html()))
