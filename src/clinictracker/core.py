# -*- coding: utf-8 -*-
# core.py
"""Main functions to fetch updates in a specified town/city."""

import asyncio
from logging import Logger
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Locator,
    TimeoutError,
)
import random
import re

import traceback
from types import TracebackType
from typing import Self, Literal

from clinictracker.selectors import HomePageSelectors, DetailPageSelectors
from clinictracker.config import Config, RunConfig, TIMEOUT_PAGE, TIMEOUT_UL
from clinictracker.models import ItemData, ListData
from clinictracker.startup import QueryParams, MyLogger, default_logger
from clinictracker.browsers import get_browser
from clinictracker.utils import (
    print_error,
    clear_content,
    construct_content,
    print_content,
    is_date_within,
)


TIMEOUT_ERR = "Timeout loading %s after %gs."
TEST_MSG = "*** Test only (no operation) ***"
BROWSER_CLOSED_MSG = "Browser closed."
NO_UPDATES_MSG = "No updates. No file exported."
NO_EXPORT_MSG = "'--no-o' selected. No file exported."


class PageManager:
    def __init__(
        self,
        browser: Browser,
        context: BrowserContext,
        query: QueryParams,
        config: Config,
        check_date: bool = True,
        logger: Logger | MyLogger = default_logger,
    ) -> None:
        self.browser: Browser = browser
        self.context: BrowserContext = context
        self.query: QueryParams = query
        self.config: Config = config
        self.check_date: bool = check_date
        self.logger: Logger | MyLogger = logger
        self.page: Page | None = None

    async def __aenter__(self) -> Self:
        self.page = await self.open_page()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        await self.close()
        return False

    async def open_page(self) -> Page:
        return await self.context.new_page()

    async def close(self) -> None:
        """Gracefully closes page."""
        if self.page and not self.page.is_closed():
            try:
                await asyncio.wait_for(self.page.close(), timeout=2)
            except asyncio.TimeoutError:
                self.logger.debug("Page closing timeout.")
            except Exception:
                pass

    @staticmethod
    async def goto_page(page: Page, url: str) -> None:
        """Navigates to a page."""
        try:
            await page.goto(url, wait_until='domcontentloaded')
        except TimeoutError:
            raise TimeoutError(
                TIMEOUT_ERR % (url, TIMEOUT_PAGE / 1000)
            ) from None
        except Exception as e:
            raise RuntimeError(f"Unable to load {url}.") from e

    async def _find_empty_sign(self, locator: Locator) -> str:
        try:
            _empty_text: str = (
                await locator.inner_text(timeout=TIMEOUT_UL)
            ).strip()
            return _empty_text
        except TimeoutError:
            _timeout = 2 * TIMEOUT_UL
            raise TimeoutError(
                TIMEOUT_ERR % ('updates', _timeout / 1000)
            ) from None

    async def get_list(self) -> ListData:
        """Navigates to the page and collects the list items.

        Returns:
            data (ListData): (items, n_tot, query)
        """
        url = self.query.url
        city = self.query.city
        days_back = self.query.days_back
        nmax = self.query.nmax
        tz = self.query.tz

        if not self.page:
            self.page = await self.open_page()

        await self.goto_page(self.page, url)
        self.logger.info(f"Page loaded: {self.page.url} (tz: {tz or 'local'})")

        # Find the <strong>Updates regarding...</strong> element,
        # then navigate to following sibling <ul>
        container_locator = self.page.locator(
            HomePageSelectors.CONTAINER
        ).describe("Container")
        title_locator = container_locator.locator(
            HomePageSelectors.TITLE
        ).describe("Page title")
        list_title_locator = container_locator.locator(
            HomePageSelectors.LIST_TITLE
        ).describe("List title")
        # list_locator = container_locator.locator(HomePageSelectors.LIST).first
        list_locator = container_locator.get_by_role('list').first.describe(
            "List"
        )
        # items_locator = list_locator.locator(HomePageSelectors.ITEM)
        items_locator = list_locator.get_by_role('listitem').describe(
            "List items"
        )
        empty_sign_locator = container_locator.locator(
            HomePageSelectors.EMPTY_SIGN
        ).describe("No updates sign")

        # Wait for the title to be loaded
        try:
            _title = (await title_locator.inner_text()).strip()
            self.logger.debug(f"Page title: {_title}")
        except TimeoutError:
            raise TimeoutError(
                TIMEOUT_ERR % ('title', TIMEOUT_PAGE / 1000)
            ) from None

        # Wait for the list title to be loaded
        try:
            _list_title = (await list_title_locator.inner_text()).strip()
            self.logger.debug(f"List title: {_list_title}")
        except TimeoutError:
            raise TimeoutError(
                TIMEOUT_ERR % ('list', TIMEOUT_PAGE / 1000)
            ) from None

        n_tot: int = 0  # total number of updates on the page
        items: list[ItemData] = []

        # Wait for the list items to be loaded
        _timeout: bool = False
        try:
            # If at least one <li> is loaded
            await items_locator.first.wait_for(
                state="visible", timeout=TIMEOUT_UL
            )
            n_tot = await items_locator.count()
        except TimeoutError:
            _timeout = True
        else:
            self.logger.info(f"{n_tot} items loaded.")

        if _timeout:
            # Look for "There is no recent news/alerts for this town."
            _empty_text = await self._find_empty_sign(empty_sign_locator)
            self.logger.info(_empty_text)
            return ListData(items=items, n_tot=n_tot, query=self.query)

        # Get items
        self.logger.info(
            f"Checking updates in {city} "
            + (f"in the past {days_back} days " if self.check_date else '')
            + f"(collecting {nmax}/{n_tot} items)..."
        )
        count = 0
        _item_data: ItemData
        for item_locator in await items_locator.all():
            if count >= nmax:
                break

            # Parse each item
            _item_data = await self.parse_item(item_locator)

            _to_collect: bool = not self.check_date
            # If within the time range, append the item to the list
            if self.check_date:
                try:
                    _to_collect = is_date_within(
                        _item_data.date, days_back, tz=tz
                    )
                except Exception as e:
                    # If errors occur, warn and collect it later
                    self.logger.warning(f"{type(e).__name__}: {e}")
                    _to_collect = True

            # If no valid date found or not checking the dates, append
            if _to_collect:
                items.append(_item_data)
                count += 1

            # Pause for a random interval
            await asyncio.sleep(random.uniform(1, 3))

        self.logger.info(f"✓ Collected {len(items)} updates from: {city}")
        return ListData(items=items, n_tot=n_tot, query=self.query)

    async def parse_item(self, item_locator: Locator) -> ItemData:
        """Parses pages and retrieves the content of this item.

        Returns:
            data (ItemData): (title, url, date, content, digest)
        """
        # Get title and link of the item from the current page
        try:
            link_locator = item_locator.get_by_role('link').describe(
                "Detail link"
            )
            title = (await link_locator.inner_text()).strip()
            url = (await link_locator.get_attribute('href')) or ''
        except Exception as e:
            raise RuntimeError(
                "(parse_item) Unable to get the item link."
            ) from e

        # Get post date by searching for '(Posted {date})'
        date_pattern = r"\(\s*[Pp]osted\s+([^\)]*)\s*\)"
        match = re.search(date_pattern, await item_locator.inner_text())
        date = '' if match is None else match.group(1).strip()

        # Get title, date, and content from the detail page in a new tab
        detail_data: ItemData
        try:
            detail_data = await self.get_details(url)
        except Exception as e:
            # If failed, set the content to empty and go on
            self.logger.warning(
                f"Problems encountered when getting details:\n{e}\n"
                "Empty content will be returned."
            )
            return ItemData(title=title, url=url, date=date)

        # Update title and date
        if detail_data.title and detail_data.title != title:
            title = detail_data.title
        if detail_data.date and detail_data.date != date:
            date = detail_data.date

        return ItemData(
            title=title, url=url, date=date, content=detail_data.content
        )

    async def get_details(self, url: str) -> ItemData:
        """Retrieves content on detail page.

        Returns:
            ItemData: A namedtuple with fields:
                title: str
                url: str
                date: str
                content: str
                digest: str
        """
        if not url.strip():
            raise ValueError("(get_details) No link to the detail page.")

        # Create a new page (tab)
        new_page = await self.open_page()

        try:
            await self.goto_page(new_page, url)
            self.logger.debug(f"Detail page loaded in new tab: {new_page.url}")
            title_locator = new_page.locator(
                DetailPageSelectors.TITLE
            ).describe("Detail title")
            title = (await title_locator.inner_text()).strip()
            date_locator = (
                new_page.locator(DetailPageSelectors.DATE_PARENT)
                .get_by_role('time')
                .describe("Detail date")
            )
            date = (await date_locator.inner_text()).strip()
            content_locator = new_page.locator(
                DetailPageSelectors.CONTENT
            ).describe("Detail content")
            content = clear_content(await content_locator.inner_html())
        except Exception:  # propagate to upper level
            raise
        finally:
            if new_page:
                await new_page.close()

        return ItemData(title=title, url=url, date=date, content=content)


async def close_everything(
    browser: Browser,
    context: BrowserContext,
    logger: Logger | MyLogger = default_logger,
) -> None:
    """Gracefully closes everything."""
    if context:
        try:
            await asyncio.wait_for(context.close(), timeout=2)
        except asyncio.TimeoutError:
            logger.debug("Context closing timeout.")
        except Exception:
            pass
    if browser:
        try:
            await asyncio.wait_for(browser.close(), timeout=2)
        except asyncio.TimeoutError:
            logger.debug("Browser closing timeout.")
        except Exception:
            pass
    logger.info(BROWSER_CLOSED_MSG)


async def run(
    queries: list[QueryParams],
    config: Config,
    logger: Logger | MyLogger = default_logger,
    check_date: bool = True,
) -> list[ListData] | None:
    """Main function to run the application."""
    data_all: list[ListData] = []
    browser: Browser | None = None

    # Let playwright close browser automatically
    async with async_playwright() as p:
        browser = await get_browser(p, config, logger)
        if browser is None:
            logger.error(
                f"{config.browser_name} not launched: unknown error occurred."
            )
            raise RuntimeError

        try:
            context = await browser.new_context()  # incognito
            context.set_default_timeout(TIMEOUT_PAGE)

            _list_data: ListData
            for i, query in enumerate(queries):
                async with PageManager(
                    browser, context, query, config, check_date, logger
                ) as pm:
                    if config.test:
                        logger.info(TEST_MSG)
                        return None

                    # Go to the landing page and get data -------------|
                    _list_data = await pm.get_list()
                    data_all.append(_list_data)

                    if not isinstance(config, RunConfig):
                        continue

                    # Print to STDOUT if selecting '--print' ----------|
                    if config.to_stdout:
                        print_content(
                            _list_data.items, _list_data.n_tot, query
                        )

                    if not config.export:
                        logger.info(NO_EXPORT_MSG)
                        continue

                    if not _list_data.items:
                        logger.info(NO_UPDATES_MSG)
                        continue

                    # Export to a file if not selecting '--no-o' ------|
                    content = construct_content(
                        _list_data.items, _list_data.n_tot, query
                    )
                    _outpath = config.output_path
                    _outpath.parent.mkdir(parents=True, exist_ok=True)
                    if len(queries) > 1:
                        _outpath = (
                            _outpath.parent
                            / f"{_outpath.stem}_{i}{_outpath.suffix}"
                        )
                    with open(_outpath, "w") as f:
                        f.write(content)
                    logger.info(f"Exported to '{str(_outpath)}'")

        except TimeoutError as e:
            print_error(e, logger, max_level=2)
            raise

        # Chained exceptions are handled here
        except RuntimeError as e:
            print_error(e, logger)
            raise

        # Other unexpected exceptions
        except Exception as e:
            if config.debug:
                traceback.print_exc()
            else:
                print_error(e, logger)
            raise

        else:
            logger.info("Done!")
            return data_all

        # Cleanup
        finally:
            await close_everything(browser, context, logger)
