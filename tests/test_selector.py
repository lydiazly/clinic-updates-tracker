# -*- coding: utf-8 -*-
# tests/test_selector.py
# pytest tests/test_selector.py --browser-channel chromium -s
import os
from playwright.sync_api import Page, expect

from clinictracker.selectors import HomePageSelectors, DetailPageSelectors
from clinictracker.utils import sanitize_content, html_to_plain


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
    assert (
        "Family Clinics in"
        in container.locator(HomePageSelectors.TITLE).inner_text()
    )
    # print(
    #     "\nTitle on landing page: "
    #     + container.locator(HomePageSelectors.TITLE).inner_text()
    # )

    title = container.locator(HomePageSelectors.LIST_TITLE)
    expect(title, "List title not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )
    assert "Updates regarding" in title.inner_text()
    # print("List title on landing page: " + title.inner_text())

    # list = container.locator(HomePageSelectors.LIST).first
    # list = container.locator(HomePageSelectors.LIST).locator('nth=0')
    list = container.get_by_role('list').first
    expect(list, "List not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )

    # items = list.locator(HomePageSelectors.ITEM)
    items = list.get_by_role('listitem')
    expect(items.first, "Item not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )
    assert items.count() == 2
    # print(f"{items.count()} items on landing page:")
    for item in items.all():
        assert "https://" in item.get_by_role('link').get_attribute('href')
    #     print(item.get_by_role("link").inner_text())
    #     print(item.get_by_role("link").get_attribute("href"))

    text = container.locator(HomePageSelectors.EMPTY_SIGN)
    expect(text, "Text not found on landing page").to_be_visible(
        timeout=TIMEOUT
    )
    assert text.inner_text() == "There is no recent news/alerts for this town."
    # print("Text on landing page: " + text.inner_text())


def test_selectors_detail(page: Page):
    """Tests selectors on detail page using sample HTML."""
    # Load HTML file
    html_file_path = os.path.abspath("./tests/sample2.html")
    page.goto(f"file://{html_file_path}")

    title = page.locator(DetailPageSelectors.TITLE)
    expect(title, "Title not found on detail page").to_be_visible(
        timeout=TIMEOUT
    )
    assert title.inner_text() == "Detail title"
    # print("\nTitle on detail page: " + title.inner_text())

    # date = page.locator(DetailPageSelectors.DATE)
    date = page.locator(DetailPageSelectors.DATE_PARENT).get_by_role('time')
    expect(date, "Date not found on detail page").to_be_visible(
        timeout=TIMEOUT
    )
    assert date.inner_text() == "September 1, 2025"
    # print("Date on detail page: " + date.inner_text())

    content = page.locator(DetailPageSelectors.CONTENT)
    expect(content, "Content not found on detail page").to_be_visible(
        timeout=TIMEOUT
    )
    substring_in_html_list = [
        "<p>",
        "<strong>",
        "<a href",
        "<br>",
        ">Clinic Website<",
        ">Contact Information &amp; Map<",
    ]
    content_html = sanitize_content(content.inner_html())
    content_plain = html_to_plain(content.inner_html())
    assert len(content_html.split('\n')) == 4
    # print("Content:")
    # print(content.inner_html())
    # print("Cleared content:")
    # print(content_html)
    # print("Plain text content:")
    # print(content_plain)
    assert all(
        [
            s in content_html and s not in content_plain
            for s in substring_in_html_list
        ]
    )
