# -*- coding: utf-8 -*-
# core.py
"""Main functions to fetch updates in a specified town/city."""
from logging import Logger, getLogger
from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    Locator,
    TimeoutError,
)
import random
import re
from time import sleep
import traceback

from clinictracker.selectors import (
    HomePageSelectors,
    DetailPageSelectors,
)
from clinictracker.config import RunConfig, TIMEOUT_PAGE, TIMEOUT_UL
from clinictracker.startup import QueryParams, MyLogger
from clinictracker.browsers import get_browser
from clinictracker.utils import (
    clear_content,
    construct_content,
    print_content,
    is_date_within,
)
from clinictracker.models import (
    Result,
    ItemData,
    ListData,
)


TIMEOUT_ERR_TEMPLATE = "Timeout loading %s after %gs."
TEST_MSG = "*** Test only (no operation) ***"
CLOSED_MSG = "Browser closed."
NO_UPDATES_MSG = "No updates. No file exported."
NO_EXPORT_MSG = "'--no-o' selected. No file exported."


def print_error(
    exc: Exception | BaseException,
    logger: Logger | MyLogger,
    max_level: int = 5,
) -> None:
    """Prints error messages and causes."""
    current_exc = exc
    level = 1
    while current_exc is not None and level <= max_level:
        logger.error(f"{'  └─ ' if level > 1 else ''}{current_exc}")
        if current_exc.__cause__ is not None:
            current_exc = current_exc.__cause__
            level += 1
        elif current_exc.__context__ is not None:
            current_exc = current_exc.__context__
            level += 1
        else:
            return


def close_everything(
    browser: Browser, context: BrowserContext, logger: Logger | MyLogger
) -> None:
    """Gracefully closes everything."""
    context.close()
    browser.close()
    logger.info(CLOSED_MSG)


def navigate_to_page(page: Page, url: str) -> None:
    """Navigates to the page."""
    try:
        page.goto(url)
        page.wait_for_load_state("networkidle")
    except TimeoutError:
        raise TimeoutError(TIMEOUT_ERR_TEMPLATE % (url, TIMEOUT_PAGE / 1000))
    except Exception as e:
        raise RuntimeError(f"Unable to load {url}.") from e


def get_list(
    page: Page,
    query: QueryParams,
    logger: Logger | MyLogger,
    check_date: bool = True,
) -> Result[ListData]:
    """Navigates to the page and collects the list items.

    Returns:
        Result: A namedtuple with fields:
            data (ListData): (items, n_tot, query)
            messages (list[str])
            warnings (list[str])
    """
    navigate_to_page(page, query.url)
    logger.info(f"Page loaded: {query.url} (tz: {query.tz or 'local'})")

    # Find the <strong>Updates regarding...</strong> element,
    # then navigate to following sibling <ul>
    container_locator = page.locator(HomePageSelectors.CONTAINER)
    title_locator = container_locator.locator(HomePageSelectors.TITLE)
    list_title_locator = container_locator.locator(
        HomePageSelectors.LIST_TITLE
    )
    list_locator = container_locator.locator(HomePageSelectors.LIST).locator(
        "nth=0"
    )  # .first
    empty_cue_locator = container_locator.locator(HomePageSelectors.EMPTY_CUE)

    # Wait for the title to be loaded
    try:
        title_locator.wait_for(state="visible")
    except TimeoutError:
        raise TimeoutError(
            TIMEOUT_ERR_TEMPLATE % ('title', TIMEOUT_PAGE / 1000)
        )
    else:
        logger.info(f"Page title: {title_locator.inner_text().strip()}")

    # Wait for the list title to be loaded
    try:
        list_title_locator.wait_for(state="visible")
    except TimeoutError:
        raise TimeoutError(
            TIMEOUT_ERR_TEMPLATE % ('list', TIMEOUT_PAGE / 1000)
        )
    else:
        logger.info(f"List title: {list_title_locator.inner_text().strip()}")

    n_tot: int = 0  # total number of updates on the page
    items: list[ItemData] = []
    messages: list[str] = []
    warnings: list[str] = []

    # Wait for the list to be loaded
    try:
        list_locator.wait_for(state="visible", timeout=TIMEOUT_UL)
        items_locator = list_locator.locator(HomePageSelectors.ITEM)
        # If at least one <li> is loaded
        items_locator.locator("nth=0").wait_for(
            state="visible", timeout=TIMEOUT_UL
        )
    except TimeoutError:
        # First, look for "There is no recent news/alerts for this town."
        try:
            empty_cue_locator.wait_for(state="visible", timeout=TIMEOUT_UL)
            messages.append(empty_cue_locator.inner_text().strip())
            return Result(
                data=ListData(items=items, n_tot=n_tot, query=query),
                messages=messages,
                warnings=warnings,
            )
        # Now timeout
        except TimeoutError:
            raise TimeoutError(
                TIMEOUT_ERR_TEMPLATE
                % ('updates', (TIMEOUT_PAGE + TIMEOUT_UL) / 1000)
            )
    else:
        n_tot = items_locator.count()
        logger.info(f"List with {n_tot} items loaded.")

    # Get items
    logger.info(
        "Checking updates "
        + (f"in the past {query.days_back} days " if check_date else '')
        + f"(collecting {query.nmax}/{n_tot} items at most)..."
    )
    count = 0
    res: Result[ItemData]
    for item_locator in items_locator.all():
        if count >= query.nmax:
            break

        # Parse each item
        try:
            res = parse_item(page, item_locator)
        except Exception as e:
            raise RuntimeError(
                f"(get_list) Unable to parse item {count + 1}."
            ) from e
        else:
            for warn in res.warnings:
                logger.warning(warn)
            for msg in res.messages:
                logger.info(msg)

        has_valid_date = False
        # If within the time range, append the item to the list
        if check_date:
            is_within_res: Result[bool]
            try:
                is_within_res = is_date_within(
                    res.data.date, query.days_back, tz=query.tz
                )
            except Exception as e:
                # If errors occur, warn and collect it later
                logger.warning(f"{type(e).__name__}: {e}")
            else:
                has_valid_date = True
                for warn in is_within_res.warnings:
                    logger.warning(warn)
                for msg in is_within_res.messages:
                    logger.info(msg)
                if is_within_res.data:
                    items.append(res.data)
                    count += 1
                else:
                    break
        elif res.data.date.strip():
            has_valid_date = True

        # If no valid date found, still append
        if not has_valid_date:
            logger.warning("Date unknown. Still collecting...")
            items.append(res.data)
            count += 1
        # If not checking the dates, append
        elif not check_date:
            items.append(res.data)
            count += 1

        # Pause for a random interval
        sleep(random.uniform(1, 3))

    return Result(
        data=ListData(items=items, n_tot=n_tot, query=query),
        messages=[f"{len(items)} updates collected."],
        warnings=[],
    )


def parse_item(page: Page, item_locator: Locator) -> Result[ItemData]:
    """Parses the page (and detail page) and retrieves the content this item.

    Returns:
        Result: A namedtuple with fields:
            data (ItemData): (title, url, date, content, digest)
            messages (list[str])
            warnings (list[str])
    """
    # Get title and link of the item from the current page
    try:
        link_locator = item_locator.get_by_role("link")
        title = link_locator.inner_text().strip() or "No Title"
        url = link_locator.get_attribute("href") or ''
    except Exception as e:
        raise RuntimeError("(parse_item) Unable to get the item link.") from e

    # Get post date by searching for '(Posted {date})'
    date_pattern = r"\(\s*[Pp]osted\s+([^\)]*)\s*\)"
    match = re.search(date_pattern, item_locator.inner_text())
    date = '' if match is None else match.group(1).strip()

    # Get title, date, and content from the detail page in a new tab
    messages: list[str] = []
    warnings: list[str] = []
    detail_data: ItemData
    try:
        detail_data = get_details(page, url)
    except Exception as e:
        # If failed, set the content to empty and go on
        warnings.append(
            f"Problems encountered when getting details:\n{e}\n"
            "Empty content will be returned."
        )
        return Result(
            data=ItemData(title=title, url=url, date=date),
            messages=messages,
            warnings=warnings,
        )
    else:
        messages.append(f"Detail page parsed in a new tab: {url}")

    # Update title and date
    if detail_data.title and detail_data.title != title:
        title = detail_data.title
    if detail_data.date and detail_data.date != date:
        date = detail_data.date

    return Result(
        data=ItemData(
            title=title, url=url, date=date, content=detail_data.content
        ),
        messages=messages,
        warnings=warnings,
    )


def get_details(page: Page, url: str) -> ItemData:
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

    # Get the current context to create a new page (tab)
    context = page.context
    # Create a new page (tab)
    new_page = context.new_page()

    try:
        navigate_to_page(new_page, url)
    except Exception:  # handle in upper level
        raise
    else:
        title_locator = new_page.locator(DetailPageSelectors.TITLE)
        title = title_locator.inner_text().strip()
        date_locator = new_page.locator(DetailPageSelectors.DATE)
        date = date_locator.inner_text().strip()
        content_locator = new_page.locator(DetailPageSelectors.CONTENT)
        content = clear_content(content_locator.inner_html())
    finally:
        new_page.close()

    return ItemData(title=title, url=url, date=date, content=content)


def run(
    query: QueryParams,
    config: RunConfig,
    logger: Logger | MyLogger = getLogger(),
    check_date: bool = True,
) -> ListData | None:
    """Main function to run the application."""
    with sync_playwright() as p:
        browser = get_browser(p, config, logger)
        if browser is None:
            logger.error(
                f"{config.browser_name} not launched: unknown error occurred."
            )
            raise RuntimeError

        context = browser.new_context()  # incognito
        page = context.new_page()
        context.set_default_timeout(TIMEOUT_PAGE)

        # Do everything in the block for cleanup on exit
        try:
            if config.test:
                logger.info(TEST_MSG)
                return None

            # Go to the landing page and get data ---------------------|
            res = get_list(page, query, logger, check_date)
            list_data = res.data

            for warn in res.warnings:
                logger.warning(warn)
            for msg in res.messages:
                logger.info(msg)

            # Print to STDOUT if selecting '--print' ------------------|
            if config.to_stdout:
                print_content(list_data.items, list_data.n_tot, query)

            # Export to a file if not selecting '--no-o' --------------|
            if config.export:
                if len(list_data.items) > 0:
                    content = construct_content(
                        list_data.items, list_data.n_tot, query
                    )
                    # os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    config.output_path.parent.mkdir(
                        parents=True, exist_ok=True
                    )
                    with open(config.output_path, "w") as f:
                        f.write(content)
                    logger.info(f"Exported to '{str(config.output_path)}'")
                else:
                    logger.info(NO_UPDATES_MSG)
            else:
                logger.info(NO_EXPORT_MSG)

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
            return list_data

        # Cleanup
        finally:
            close_everything(browser, context, logger)
