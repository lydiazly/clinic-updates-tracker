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
from clinictracker.startup import MyLogger
from clinictracker.user.startup import (
    QueryParamsForAll,
    load_query_for_all,
    load_query_for_each,
)
from clinictracker.user.helpers import (
    load_users_from_json,
    save_users_to_json,
    prompt_to_confirm,
)
from clinictracker.core import run, print_error, TEST_MSG
from clinictracker.utils import construct_content
from clinictracker.user.db_manager import UserServiceDB, initialize_db
from clinictracker.user.email_service import EmailService


CREATION_ONLY_MSG = "*** Creation only (no data fetching) ***"
UPSERT_ONLY_MSG = "*** Upsert only (no data fetching) ***"
SKIP_CREATION_MSG = "'--skip-creation' selected. Table creation skipped."


def get_lists_for_all(
    query_all: QueryParamsForAll,
    config: ServiceConfig,
    logger: Logger | MyLogger,
) -> dict[str, ListData]:
    """Fetches data in all cities.
    Calls `core.run(query, config, logger, check_date=False)`"""
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
        body_to_send = res['body']
        hashes_to_record = res['hashes']
        if not body_to_send or hashes_to_record:
            continue

        # Send items to user
        current_time = datetime.now()
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
    current_time = datetime.now()
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
    # Retrieve all current users in database
    users_db: list[User] = db.get_all_users()
    logger.info(f"Total users in database: {len(users_db)}")

    # Load data from JSON file and upsert
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
                if prompt_to_confirm(
                    "**CAUTION** About to delete users in database that "
                    "are not in the JSON file"
                ):
                    username_set_src = {user.username for user in users_src}
                    username_set_db = {user.username for user in users_db}
                    username_diff = username_set_db - username_set_src
                    logger.info(
                        f"Deleting {len(username_diff)} users in database..."
                    )
                    for username in username_diff:
                        db.delete_user(username)
                else:
                    logger.info("Operation cancelled.")
        else:
            logger.info("Skipping updating users in database...")

    # Handle commands
    if config.command is not None:
        match config.command.name:
            case CommandName.LIST:
                pass  # print later

            case CommandName.ADD:
                if config.load_users:
                    pass
                users: list[User] = config.command.data
                logger.info(f"Inserting {len(users)} users into database...")
                db.insert_users(users)

            case CommandName.UPD:
                if config.load_users:
                    pass
                user_dicts: list[dict[str, Any]] = config.command.data
                logger.info(f"Updating {len(user_dicts)} users in database...")
                for user in user_dicts:
                    db.update_user(user.pop('username'), user)

            case CommandName.DEL:
                if config.load_users:
                    pass
                usernames: list[str] = config.command.data
                logger.info(f"Deleting {len(usernames)} users in database...")
                for username in usernames:
                    db.delete_user(username)

            case CommandName.RESET:
                if prompt_to_confirm(
                    "**CAUTION** About to reset user id sequence in database"
                ):
                    db.reset_id_seq()

            case CommandName.CLEAR:
                if config.load_users:
                    pass
                if prompt_to_confirm(
                    "**CAUTION** About to empty all tables and "
                    "reset user id sequence"
                ):
                    db.truncate_tables(cascade=False, restart_identity=True)

            case _:
                raise ValueError(
                    f"Unknown command: {config.command.name}\n"
                    f"Valid commands: {', '.join(name for name in CommandName)}"
                )

    # Retrieve all users again
    if users_src or config.command.name in [
        CommandName.ADD,
        CommandName.UPD,
        CommandName.DEL,
        CommandName.CLEAR,
    ]:
        users_db = db.get_all_users()
        logger.info(f"Total users in database: {len(users_db)}")

    # Print all users in database
    users_str = "Current users in database:\n" + '\n'.join(
        f"{'-' * 60}\n#{i}\n{user!s}\n{'-' * 60}"
        for i, user in enumerate(users_db)
    )
    if config.command == CommandName.LIST:
        logger.info(users_str)
    else:
        logger.debug(users_str)

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

            if config.upsert_only:
                logger.info(UPSERT_ONLY_MSG)
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
                fetch_data_and_send(db, users, query_all, config, logger)

                # Cleanup old records
                stale_days = query_all.max_days_back + CLEANUP_BUFFER_DAYS
                logger.info(f"Cleaning up records >= {stale_days} days...")
                cutoff_date = datetime.now() - timedelta(days=stale_days)
                db.cleanup_old_sent_items(cutoff_date)
                sent_items_count = db.count_all_sent_items()
                logger.info(f"Current records: {sent_items_count}")

            # Save user objects to JSON -------------------------------|
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
