# -*- coding: utf-8 -*-
# user/user_service.py
"""User service."""
from datetime import datetime, timedelta
from logging import Logger, getLogger
import traceback
from typing import Any

from clinictracker.user.config import (
    CommandName,
    ServiceConfig,
    CLEANUP_BUFFER_DAYS,
)
from clinictracker.models import ItemData, ListData
from clinictracker.user.models import User
from clinictracker.startup import MyLogger, Color
from clinictracker.user.startup import (
    QueryParamsForAll,
    load_query_for_all,
    load_query_for_each,
)
from clinictracker.user.helpers import (
    load_users_from_json,
    save_users_to_json,
    prompt_to_confirm,
    users_to_str,
    user_updates_to_str,
)
from clinictracker.core import run, print_error, TEST_MSG
from clinictracker.utils import construct_content
from clinictracker.user.db_manager import UserServiceDB, initialize_db
from clinictracker.user.email_service import EmailService


CREATION_ONLY_MSG = "*** Creation only (no data fetching) ***"
CRUD_ONLY_MSG = "*** CRUD only (no data fetching) ***"
SKIP_CREATION_MSG = "'--skip-creation' selected. Table creation skipped."
ABORT_MSG = "Operation cancelled."
CAUTION_FLG = f"{Color.YELLOW}**CAUTION**{Color.END} "


def get_lists_for_all(
    query_all: QueryParamsForAll,
    config: ServiceConfig,
    logger: Logger | MyLogger,
) -> dict[str, ListData]:
    """Fetches data in all cities.
    Calls `core.run(query, config, logger, check_date=False)`
    """
    list_data: ListData
    data_all: dict[str, ListData] = {}
    for city in query_all.cities:
        query = load_query_for_each(
            config, city, query_all.max_days_back, query_all.max_nmax
        )
        list_data = run(
            query=query, config=config, logger=logger, check_date=False
        )
        data_all[city] = list_data
        if len(list_data.items) > 0:
            logger.info(f"Collected {list_data.n_tot} items from: {city}")
        else:
            logger.info(f"No updates from {city}.")
    return data_all


def fetch_data_and_send(
    db: UserServiceDB,
    users: list[User],
    query_all: QueryParamsForAll,
    config: ServiceConfig,
    logger: Logger | MyLogger,
) -> None:
    """Fetches full lists of data and send to users."""
    # Fetch data in all cities specified by users
    logger.info("Collecting updates for all...")
    data_all: dict[str, ListData] = get_lists_for_all(
        query_all, config, logger
    )

    # Process each user
    body_to_send: str
    hashes_to_record: list[str]
    for user in users:
        logger.info(f"Processing user {user.username}...")
        res = process_user(db, user, data_all, logger)
        body_to_send = res.get('body')
        hashes_to_record = res.get('hashes')
        if not body_to_send or hashes_to_record:
            continue

        # Send items to user
        current_time = datetime.now().astimezone()  # timezone-aware
        try:
            EmailService.send_to_user(user, body_to_send)
        except Exception as e:
            logger.error(f"Failed to send email to {user.username}:\n{e}")
            continue
        else:
            db.record_sent_items(user, hashes_to_record, current_time)
            db.update_last_sent_at(user, current_time)


def process_user(
    db: UserServiceDB,
    user: User,
    data_all: dict[str, ListData],
    logger: Logger | MyLogger,
) -> dict[str, str | list[str]]:
    """Filters data for a user and constructs the email body.
    Items are filtered by hash values instead of dates.

    Returns:
        result: A dict with keys:
            body (str): Email body to send to the user
            hashes (list[str]): List of item hash values to be sent
    """
    body_to_send: str = ''
    hashes_to_record: list[str] = []
    username: str = user.username
    nmax: int = user.nmax

    # Check if enough time has passed since last_sent_at
    current_time = datetime.now().astimezone()  # timezone-aware
    if not db.should_send_to_user(user, current_time):
        logger.info(
            f"Skipping {username}: Not enough time passed since last send."
        )
        return {'body': body_to_send, 'hashes': hashes_to_record}

    unsent_items: list[ItemData]
    email_body_list: list[str] = []
    for city in user.cities:
        logger.info(f"Filtering updates in {city} for {username}...")
        n_tot = data_all[city].n_tot
        query = data_all[city].query
        items = data_all[city].items
        hashes = [item.digest for item in items]
        unsent_items = []

        if not items:
            logger.info("No updates found.")
            continue

        # Check which items in this city have already been sent
        sent_hashes: set[str] = db.get_sent_item_hashes(user.id, hashes)
        logger.debug(
            f"Found {len(sent_hashes)} updates of {city} "
            f"have been sent to {username}."
        )

        # Get unsent items in this city and limit to nmax
        for item in items:
            if item.digest not in sent_hashes:
                unsent_items.append(item)

        items_to_send = unsent_items[:nmax]
        hashes_to_record.extend([item.digest for item in items_to_send])

        if items_to_send:
            email_body_list.append(
                construct_content(items_to_send, n_tot, query, False)
            )
            logger.debug(
                f"About to send {len(items_to_send)} new items of {city} "
                f"to {username} (at most {nmax} items)."
            )
        else:
            logger.debug(f"No unsent items in {city} for {username}.")
            continue

    if email_body_list:
        body_to_send = '\n'.join(email_body_list)
    else:
        logger.info(f"No updates for {username}.")

    return {'body': body_to_send, 'hashes': hashes_to_record}


def crud_and_get_users(
    db: UserServiceDB,
    config: ServiceConfig,
    logger: Logger | MyLogger,
) -> list[User]:
    """Performs CRUD operations then retrieves all users in database.
    - If `config.load_users` is `True`, overrides
    add/update/delete/clear commands.
    - If `config.load_users` is `True` and `config.delete_users` is `True`,
    delete the users in database that are not in the JSON file.
    """
    users_db: list[User] = []
    fetch_all: bool = True

    # Load data from JSON file and insert/update into database
    users_src: list[User] = []
    if config.load_users:
        logger.info("Loading data from JSON...")
        users_src = load_users_from_json(config.json_path, logger)
        if users_src:
            logger.info(
                f"Inserting/Updating {len(users_src)} users into database..."
            )
            db.insert_users(users_src, update=True)
            if config.delete_users:
                # Retrieve all current users in database
                users_db = db.get_all_users()
                logger.info(f"Total users in database: {len(users_db)}")
                username_set_src = {user.username for user in users_src}
                username_set_db = {user.username for user in users_db}
                username_diff = username_set_db - username_set_src
                if len(username_diff) > 0:
                    if prompt_to_confirm(
                        f"{CAUTION_FLG}About to delete users in database that "
                        f"are not in the JSON file: {', '.join(username_diff)}"
                    ):
                        logger.info(
                            f"Deleting {len(username_diff)} users "
                            "in database..."
                        )
                        for username in username_diff:
                            db.delete_user(username)
                    else:
                        logger.info(ABORT_MSG)
                else:
                    fetch_all = False
        else:
            logger.info("Skipping updating users in database...")

    # Handle commands
    if config.command is not None:
        fetch_all = False
        match config.command.name:
            case CommandName.LIST:
                usernames: list[str] | None = config.command.data
                if usernames is None:
                    fetch_all = True
                else:
                    # Retrieve specified users in database
                    for username in usernames:
                        user = db.get_user_by_username(username)
                        if user is not None:
                            users_db.append(user)
                        else:
                            logger.warning(db.USER_NOT_FOUND_MSG % username)
                    logger.info(f"Retrieved {len(users_db)} users.")
                # Print users_db later

            case CommandName.ADD:
                if config.load_users:
                    pass
                # Users in config.command.data are validated
                users: list[User] = config.command.data
                logger.info(f"Inserting {len(users)} users into database...")
                db.insert_users(users)

            case CommandName.UPD:
                if config.load_users:
                    pass
                # Users in config.command.data are validated
                updates_list: list[dict[str, Any]] = config.command.data
                logger.info(
                    f"Updating {len(updates_list)} users in database..."
                )
                for updates in updates_list:
                    username = updates.pop('username')
                    user_db = db.get_user_by_username(username)
                    if user_db is not None:
                        if prompt_to_confirm(
                            f"About to update user:\n"
                            f"{user_updates_to_str(user_db, updates)}"
                        ):
                            logger.info(f"Updating {username} in database...")
                            db.update_user(username, updates)
                        else:
                            logger.info(ABORT_MSG)
                    else:
                        logger.warning(db.USER_NOT_FOUND_MSG % username)

            case CommandName.DEL:
                if config.load_users:
                    pass
                usernames: list[str] = config.command.data
                for username in usernames:
                    user_db = db.get_user_by_username(username)
                    if user_db is not None:
                        if prompt_to_confirm(
                            f"About to delete user:\n{user_db!s}"
                        ):
                            logger.info(f"Deleting {username} in database...")
                            db.delete_user(username)
                        else:
                            logger.info(ABORT_MSG)
                    else:
                        logger.warning(db.USER_NOT_FOUND_MSG % username)

            case CommandName.RESET:
                if prompt_to_confirm(
                    f"{CAUTION_FLG}About to reset user id sequence in database"
                ):
                    logger.info("Resetting user id sequence...")
                    db.reset_id_seq()
                else:
                    logger.info(ABORT_MSG)

            case CommandName.CLEAR:
                if config.load_users:
                    pass
                tables: list[str] = config.command.data
                # Clear specified tables in database
                for tb in tables:
                    if prompt_to_confirm(
                        f"{CAUTION_FLG}About to remove all rows from "
                        f"table: {tb}"
                    ):
                        logger.info(f"Truncating {tb} in database...")
                        db.truncate_table(tb)
                    else:
                        logger.info(ABORT_MSG)

            case _:
                raise ValueError(
                    f"Unknown command: {config.command.name}\nValid commands: "
                    + ', '.join(name for name in CommandName)
                )

    # Retrieve all users after operations
    if config.save_users or fetch_all:
        users_db = db.get_all_users()
        logger.info(f"Total users in database: {len(users_db)}")

    # Print users in database
    if users_db:
        if (
            config.command is not None
            and config.command.name == CommandName.LIST
        ):
            logger.info("Users retrieved:\n" + users_to_str(users_db))
        else:
            logger.debug("All users:\n" + users_to_str(users_db))

    return users_db


def run_service(
    config: ServiceConfig, logger: Logger | MyLogger = getLogger()
) -> None:
    """Manages user data in the database and process daily updates."""
    # Initialize database
    with initialize_db(logger) as db:
        try:
            if config.test:
                logger.info(TEST_MSG)
                return

            # Create tables -------------------------------------------|
            if config.skip_creation:
                logger.info(SKIP_CREATION_MSG)
            else:
                db.create_users_table()
                db.create_sent_items_table()

            if config.creation_only:
                logger.info(CREATION_ONLY_MSG)
                return

            # Perform CRUD operations and retrieve all users ----------|
            users: list[User] = crud_and_get_users(db, config, logger)

            if config.crud_only:
                logger.info(CRUD_ONLY_MSG)
                return

            # Go fetch and send data ----------------------------------|
            if config.command is None:
                if not users:
                    logger.info("No users. Nothing to do.")
                    return

                # Settings based on all users
                query_all: QueryParamsForAll = load_query_for_all(users)
                logger.debug(
                    f"max_days_back={query_all.max_days_back}, "
                    f"max_nmax={query_all.max_nmax}"
                )
                logger.info(f"Cities to check: {', '.join(query_all.cities)}")

                # Prepare data and send to all users
                current_time = datetime.now().astimezone()  # timezone-aware
                fetch_data_and_send(db, users, query_all, config, logger)

                # Cleanup old records
                stale_days = query_all.max_days_back + CLEANUP_BUFFER_DAYS
                logger.info(
                    f"Cleaning up records more than {stale_days} days old..."
                )
                cutoff_date = current_time - timedelta(days=stale_days)
                db.cleanup_old_sent_items(cutoff_date)
                sent_items_count = db.count_all_sent_items()
                logger.info(f"Current records count: {sent_items_count}")

            # Save User objects to JSON -------------------------------|
            if config.save_users:
                save_users_to_json(users, config.json_path, logger)

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
