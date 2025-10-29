# -*- coding: utf-8 -*-
# user/models.py
"""Data models and structures."""
from dataclasses import dataclass, field
from datetime import datetime
from dotenv import load_dotenv
import os
from typing import TypedDict


load_dotenv()

# Whitelist of allowed columns for update
ALLOWED_COLS: list[str] = [
    'username',
    'nickname',
    'emails',
    'cities',
    'period',
    'nmax',
]

# Default schedule period in days
PERIOD_USER: int = int(os.getenv('PERIOD_USER', 1))  # default: 1
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
        period (int): (> 0) Schedule period in days, default to 1
        nmax (int): (> 0) Maximum number of items to collect, default to 10
        last_sent_at (datetime): Time of last sent (automatically generated)
        id (int): Assigned by database (-1: not assigned)
    """

    username: str
    nickname: str | None = None
    emails: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    period: int = PERIOD_USER
    nmax: int = MAX_ITEMS_USER
    last_sent_at: datetime | None = None
    id: int = -1

    def __str__(self) -> str:
        return '\n'.join(
            f"{field:>20}: {getattr(self, field)}"
            for field in ['id'] + ALLOWED_COLS + ['last_sent_at']
        )


class UserDict(TypedDict, total=False):
    username: str
    nickname: str | None
    emails: list[str]
    cities: list[str]
    period: int
    nmax: int
