# -*- coding: utf-8 -*-
# user/models.py
"""Data models and structures."""

from dataclasses import dataclass, field
from datetime import datetime
from dotenv import load_dotenv
import os
from typing import Any, TypedDict


load_dotenv()

# Whitelist of allowed columns for update
ALLOWED_COLS: list[str] = [
    'username',
    'nickname',
    'emails',
    'cities',
    'interval',
    'nmax',
    'is_active',
]

# Default sending interval in days
INTERVAL_USER: int = int(os.getenv('INTERVAL_USER', 1))  # default: 1
# Default number of items
MAX_ITEMS_USER: int = int(os.getenv('MAX_ITEMS_USER', 10))  # default: 10


@dataclass
class User:
    """User data as a dataclass object.

    Attributes:
        username (str): (unique, not null) Any unique string
        nickname (str): Default to null
        emails (list[str]): (non-empty) Recipient list
        cities (list[str]): (non-empty) Town/City list
        interval (int): (> 0) sending interval in days, default to 1
        nmax (int): (> 0) Maximum number of items to collect, default to 10
        is_active (bool): Default to True
        last_sent_at (datetime): Time of last sent (automatically generated)
        id (int): Assigned by database (-1: not assigned)
    """

    username: str
    nickname: str | None = None
    emails: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    interval: int = INTERVAL_USER
    nmax: int = MAX_ITEMS_USER
    is_active: bool = True
    last_sent_at: datetime | None = None
    id: int = -1

    def __str__(self) -> str:
        return '\n'.join(
            # f"{field:>20}: {getattr(self, field)}"
            f"{field:>20}: {self.print_value(getattr(self, field))}"
            for field in ['id'] + ALLOWED_COLS + ['last_sent_at']
        )

    @staticmethod
    def print_value(value: Any) -> Any:  # noqa: ANN401
        if isinstance(value, datetime):
            return value.astimezone().strftime('%Y-%m-%d %H:%M:%S (%Z)')
        else:
            return value


class UserDict(TypedDict, total=False):
    username: str
    nickname: str | None
    emails: list[str]
    cities: list[str]
    interval: int
    nmax: int
    is_active: bool
