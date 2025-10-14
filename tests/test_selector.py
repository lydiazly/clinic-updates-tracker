# -*- coding: utf-8 -*-
# tests/test_selector.py
# pytest tests/test_selector.py --browser-channel chromium -s
import os
from playwright.sync_api import Page, expect
from clinictracker.selectors import (
    HomePageSelectors,
    DetailPageSelectors,
)
from clinictracker.utils import clear_content, html_to_plain


TIMEOUT = 500


def test_selectors_home(page: Page):
    """Tests selectors on landing page using sample HTML."""
    # Load HTML file
    html_file_path = os.path.abspath("./tests/sample1.html")
    page.goto(f"file://{html_file_path}")

    container = page.locator(HomePageSelectors.CONTAINER)
    expect(container, "Container not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )
    print(
        "\nTitle on landing page: "
        + container.locator(HomePageSelectors.TITLE).inner_text()
    )

    title = container.locator(HomePageSelectors.LIST_TITLE)
    expect(title, "List title not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )
    print("List title on landing page: " + title.inner_text())

    # list = container.locator(HomePageSelectors.LIST).first
    list = container.locator(HomePageSelectors.LIST).locator('nth=0')
    expect(list, "List not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )

    items = list.locator(HomePageSelectors.ITEM)
    expect(items.first, "Item not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )
    print(f"{items.count()} items on landing page:")
    for item in items.all():
        print(item.get_by_role("link").inner_text())
        print(item.get_by_role("link").get_attribute("href"))

    text = container.locator(HomePageSelectors.EMPTY_CUE)
    expect(text, "Text not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )
    print("Text on landing page: " + text.inner_text())


def test_selectors_detail(page: Page):
    """Tests selectors on detail page using sample HTML."""
    # Load HTML file
    html_file_path = os.path.abspath("./tests/sample2.html")
    page.goto(f"file://{html_file_path}")

    title = page.locator(DetailPageSelectors.TITLE)
    expect(title, "Title not found on detail page").to_be_visible(
        timeout=TIMEOUT
    )
    print("\nTitle on detail page: " + title.inner_text())

    date = page.locator(DetailPageSelectors.DATE)
    expect(date, "Date not found on detail page").to_be_visible(
        timeout=TIMEOUT
    )
    print("Date on detail page: " + date.inner_text())

    content = page.locator(DetailPageSelectors.CONTENT)
    expect(content, "Content not found on detail page").to_be_visible(
        timeout=TIMEOUT
    )
    # print("Content:")
    # print(content.inner_html())
    print("Cleared content:")
    print(clear_content(content.inner_html()))
    print("Plain text content:")
    print(html_to_plain(content.inner_html()))
