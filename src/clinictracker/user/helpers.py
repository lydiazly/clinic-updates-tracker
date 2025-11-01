# -*- coding: utf-8 -*-
# user/helpers.py
"""User data helper functions."""
from dataclasses import asdict
from datetime import datetime
import json
from logging import Logger
from pathlib import Path
import re
from typing import Any, cast

from clinictracker.startup import trim_str, MyLogger, Color
from clinictracker.user.models import User, UserDict, ALLOWED_COLS


HR = '-' * 60  # horizontal line

NAME_LEN_MAX = 30
USERNAME_RULES = """Username rules:
- 3-30 characters
- Only contains Latin letters, numbers, underscores, hyphens,
  or is a valid email address
- Starts with a Latin letter
- Doesn't end with underscore, hyphen, or '@'
- Case insensitive
"""
EMAIL_PATTERN = re.compile(
    r'^[A-Za-z0-9][A-Za-z0-9\._%+\-]*'
    r'@[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?'
    r'(\.[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?)+$'
)
NAME_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_\-]*[a-zA-Z0-9]$')


def is_valid_email(email: str | None) -> bool:
    """Checks if a string is a valid email address."""
    if email is None:
        return False
    if len(email) > NAME_LEN_MAX:
        return False
    return bool(EMAIL_PATTERN.match(email))


def is_valid_username(username: str | None) -> bool:
    """Checks if a username is valid based on USERNAME_RULES."""
    if username is None:
        return False
    if not (3 <= len(username) <= NAME_LEN_MAX):
        return False
    return is_valid_email(username) or bool(NAME_PATTERN.match(username))


def create_user_from_dict(user_dict: UserDict) -> User:
    """Create a valid `User` object from a dict.
    If `emails` is None or empty, and `username` is a valid email address,
    add this email into `emails`.
    """
    _username: str = trim_str(user_dict.get('username', ''))
    user_dict['username'] = _username
    # If no email specified and username is an email, use it
    if not user_dict.get('emails') and is_valid_email(_username):
        user_dict['emails'] = [_username]
    user: User = get_valid_user(User(**user_dict))
    return user


def load_users_from_json(
    json_path: Path, logger: Logger | MyLogger
) -> list[User]:
    """Loads valid `User` objects from a JSON file."""
    data: list[UserDict]
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
    valid_users: list[User] = []
    for user_dict in data:
        try:
            user = create_user_from_dict(user_dict)
        except Exception as e:
            logger.warning(f"Skipping invalid user: {e}")
            continue
        else:
            valid_users.append(user)

    logger.info(f"Loaded {len(valid_users)} users from: {json_path}")
    return valid_users


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
    data: list[UserDict] = [
        cast(
            UserDict, {k: User.print_value(v) for k, v in asdict(user).items() if v is not None}
        )
        for user in users
    ]

    # Serialize as JSON, not escaping non-ASCII characters
    s = json.dumps(data, indent=2, ensure_ascii=False)

    # Format JSON with compact lists
    def _replace_func(match: re.Match[str]) -> str:
        # Split on any whitespace (\n \r \t \f \s) and discard empty strings
        return ' '.join(match.group().split())

    compact_json = re.sub(r"(?<=\[)[^\[\]\{]+(?=\])", _replace_func, s)

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


def get_valid_user(user: User) -> User:
    """Returns a valid `User` object."""
    if not user.username:
        raise ValueError(f"{asdict(user)}: 'username' is required")

    for field in ALLOWED_COLS:
        validate_user_field(user.username, field, getattr(user, field))

    return user


def get_valid_user_dict(user_dict: UserDict) -> UserDict:
    """Returns a valid user dict."""
    _username: str = trim_str(user_dict.get('username', ''))
    if not _username:
        raise ValueError(f"{user_dict}: 'username' is required")

    for k in user_dict.keys():
        validate_user_field(_username, k, user_dict.get(k))

    return user_dict


def validate_user_field(username: str, field: str, data: Any) -> None:
    """Validates a specified field of a user."""
    ERR_TEMPLATE = username + ": %s"
    match field:
        case 'username':
            if not is_valid_username(username):
                raise ValueError(
                    f"Invalid username: {username}\n{USERNAME_RULES}"
                )
        case 'nickname':
            if data and len(data) > NAME_LEN_MAX:
                raise ValueError(
                    ERR_TEMPLATE
                    % f"Maximum length of '{field}': {NAME_LEN_MAX}"
                )
        case 'emails' | 'cities':
            if not data:
                raise ValueError(ERR_TEMPLATE % f"'{field}' is null or empty.")
            if field == 'emails':
                for email in data:
                    if not is_valid_email(email):
                        raise ValueError(
                            ERR_TEMPLATE % f"Invalid email: {email}"
                        )
        case 'period' | 'nmax':
            if not isinstance(data, int) or data <= 0:
                raise ValueError(
                    ERR_TEMPLATE
                    % f"'{field}' must be a positive integer, got: {data}"
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


def users_to_str(users: list[User]) -> str:
    """Formats `User` objects."""
    users_str_list = [f"{user!s}" for user in users]
    users_str = (f"\n{HR}\n".join(['', *users_str_list, ''])).strip()
    return users_str


def user_dicts_to_str(user_dicts: list[UserDict]) -> str:
    """Formats user dicts."""
    users_str_list = [
        '\n'.join(
            f"{k:>20}: {User.print_value(user.get(k))}"
            for k in ALLOWED_COLS
            if k in user
        )
        for user in user_dicts
    ]
    users_str = (f"\n{HR}\n".join(['', *users_str_list, ''])).strip()
    return users_str


def user_updates_to_str(user: User, updates: UserDict) -> str:
    """Formats user dicts."""
    user_str = '\n'.join(
        f"{field:>20}: {User.print_value(getattr(user, field))}"
        + (
            f"{Color.YELLOW}  ->  {updates.get(field)}{Color.END}"
            if field in updates
            else ''
        )
        for field in ['id'] + ALLOWED_COLS + ['last_sent_at']
    )
    user_str = f"{HR}\n{user_str}\n{HR}"
    return user_str
