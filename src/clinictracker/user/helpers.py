# -*- coding: utf-8 -*-
# user/helpers.py
"""User data helper functions."""
from dataclasses import asdict
from datetime import datetime
import json
from logging import Logger
from pathlib import Path
import re
from typing import Any

from clinictracker.user.models import User, ALLOWED_COLS
from clinictracker.startup import MyLogger


def is_valid_email(email: str) -> bool:
    """Checks if a string is a valid email address."""
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?'
        r'(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)+$'
    )
    return bool(EMAIL_PATTERN.match(email)) if email else False


def create_user_from_dict(
    user_dict: dict[str, str | int | list[str] | None],
) -> User:
    """Create a valid User object from a dict.
    If `emails` is None or empty, and `username` is a valid email address,
    add this email into `emails`.
    """
    amended_dict: dict[str, str | list[str]] = {}
    username = user_dict['username'].strip()
    amended_dict['username'] = username
    # If no email specified and username is an email, use it
    if not user_dict['emails'] and is_valid_email(username):
        amended_dict['emails'] = [username]
    try:
        user: User = validate_user(User(**(user_dict | amended_dict)))
    except TypeError as e:
        raise TypeError(f"{user_dict | amended_dict}: {e}")
    return user


def load_users_from_json(
    json_path: Path, logger: Logger | MyLogger
) -> list[User]:
    """Loads valid user objects from a JSON file."""
    data: list[dict[str, str | int | list[str] | None]]
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"{str(json_path)}: file not found")
    except Exception as e:
        raise RuntimeError(f"Failed to load file '{str(json_path)}': {e}")
    # Validate the data
    if (
        not data
        or not isinstance(data, list)
        or any(not isinstance(d, dict) for d in data)
    ):
        raise ValueError(
            "Data in the JSON file must be a non-empty list of objects."
        )
    # Create and validate User objects
    users: list[User] = list(map(create_user_from_dict, data))
    logger.info(f"Loaded {len(users)} users from: {json_path}")
    return users


def save_users_to_json(
    users: list[User], json_path: Path, logger: Logger | MyLogger
) -> None:
    """Saves `User` objects to a JSON file, dropping `None` values.
    If the file exists, back up by renaming it with its modification time.
    """
    if not users:
        logger.info("No users to save.")
        return

    # Convert each object to dict, filtering out None values
    data: list[dict[str, str | int | list[str]]] = [
        {k: v for k, v in asdict(user).items() if v is not None}
        for user in users
    ]

    # Serialize as JSON, not escaping non-ASCII characters
    s = json.dumps(data, indent=2, ensure_ascii=False)

    # Format JSON with compact lists
    def replace_func(match: re.Match[str]) -> str:
        # Split on any whitespace (\n \r \t \f \s) and discard empty strings
        return ' '.join(match.group().split())

    compact_json = re.sub(r"(?<=\[)[^\[\]\{]+(?=\])", replace_func, s)

    # If file exists and non-empty, create backup
    if json_path.is_file() and json_path.stat().st_size > 0:
        mtime = datetime.fromtimestamp(json_path.stat().st_mtime)
        mtime_str = mtime.strftime('%Y%m%d%H%M%S')
        backup_name = f"{json_path.stem}_{mtime_str}{json_path.suffix}"
        backup_path = json_path.parent / backup_name
        json_path.rename(backup_path)
        logger.info(f"Backed up existing file to: {backup_name}")

    # Save to file
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write(compact_json)
    logger.info(f"Saved {len(users)} users to: {json_path}")


def validate_user(user: User) -> User:
    """Validates all fields of a user."""
    for field in ALLOWED_COLS[1:]:  # exclude 'username'
        validate_user_field(user.username, field, getattr(user, field))
    return user


def validate_user_field(username: str, field: str, data: Any) -> None:
    """Validates a specified field of a user."""
    ERR_TEMPLATE = username + ": %s"
    match field:
        case 'emails':
            if not data:
                raise ValueError(ERR_TEMPLATE % "'emails' is null or empty")
            for email in data:
                if not is_valid_email(email):
                    raise ValueError(ERR_TEMPLATE % f"Invalid email: {email}")
        case 'cities':
            if not data:
                raise ValueError(ERR_TEMPLATE % "'cities' is null or empty")
        case 'period':
            if data <= 0:
                raise ValueError(
                    ERR_TEMPLATE % f"'period' must be positive, got {data}"
                )
        case 'nmax':
            if data <= 0:
                raise ValueError(
                    ERR_TEMPLATE % f"'nmax' must be positive, got {data}"
                )


def prompt_to_confirm(description: str) -> bool:
    """Prompts to confirm an action."""
    prompt = '\n'.join([description, "Continue? (y/N): "])
    while True:
        response = input(prompt).lower().strip()
        if response in ['', 'n']:
            return False
        elif response == 'y':
            return True
        else:
            print("Please enter 'y' or 'n' (or press Enter for No).")
