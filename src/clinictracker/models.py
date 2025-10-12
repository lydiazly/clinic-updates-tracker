# -*- coding: utf-8 -*-
# models.py
"""Data models and structures."""
from typing import TypeVar, Generic, NamedTuple


T = TypeVar('T')


class Result(NamedTuple, Generic[T]):
    """For passing result data and messages.

    Args:
        data (T): Any data
        messages (list[str]): Each message will be printed by logger.info()
        warnings (list[str]): Each warning will be printed by logger.warning()
    """
    data: T
    messages: list[str]
    warnings: list[str]


class ItemData(NamedTuple):
    """Item data.

    Args:
        title (str): Title of the item
        url (str): URL to the detail page of this item
        date (str): Post date
        content (str): The HTML content on the detail page of the item
    """
    title: str
    url: str
    date: str
    content: str


class ListData(NamedTuple):
    """List data.

    Args:
        item_list (list[ItemData]): List of item objects
        n_tot (int): Total number of items on the page
    """
    item_list: list[ItemData]
    n_tot: int


class QueryParams(NamedTuple):
    """Query parameters.

    Args:
        url (str): The target full URL
        city (str): The town/city to be queried
        days_back (int): Number of days to look back for data collection
        nmax (int): Maximum number of items to collect
        tz (str): TZ identifier (IANA Time Zones) of the target website
    """
    url: str
    city: str
    days_back: int
    nmax: int
    tz: str
