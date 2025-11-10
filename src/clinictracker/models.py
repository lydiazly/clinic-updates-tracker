# -*- coding: utf-8 -*-
# models.py
"""Data models and structures."""

from dataclasses import dataclass, field
import hashlib
from logging import LogRecord
from typing import NamedTuple

from clinictracker.startup import QueryParams


@dataclass(frozen=True)
class ItemData:
    """Item data as an immutable dataclass object.

    Attributes:
        title (str): Title of the item
        url (str): URL to the detail page of this item
        date (str): Post date
        content (str): The HTML content on the detail page of the item
        digest (str): Hash value generated from title, url, and date
            (different from `hash()`)
    """

    title: str
    url: str = ''
    date: str = ''
    content: str = ''
    digest: str = field(default='', init=False, repr=False)

    @staticmethod
    def _generate_digest(title: str, url: str, date: str) -> str:
        """Generates SHA-256 hash from item title, url, and date."""
        content: str = '|'.join([title.strip(), url.strip(), date.strip()])
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def __post_init__(self) -> None:
        digest_value = self._generate_digest(self.title, self.url, self.date)
        object.__setattr__(self, 'digest', digest_value)


class ListData(NamedTuple):
    """Named tuple for wrapping item list, total number, and query.

    Attributes:
        items (list[ItemData]): List of item objects
        n_tot (int): Total number of items on the page
        query (QueryParams): Query parameters for a city
    """

    items: list[ItemData]
    n_tot: int
    query: QueryParams


class TaskResult(NamedTuple):
    """For passing results and log records of a task.

    Attributes:
        task_id (int): Task ID
        data (ListData | None): List data
        records (list[LogRecord]): Log records
    """

    task_id: int
    data: ListData | None
    records: list[LogRecord]
