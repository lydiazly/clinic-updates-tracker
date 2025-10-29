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
    DAYS_BACK_MIN,
    MAX_ITEMS_MIN,
    CLEANUP_BUFFER_DAYS,
)
from clinictracker.models import ItemData, ListData
from clinictracker.user.models import User
from clinictracker.startup import MyLogger, Color, QueryParams, get_full_url
from clinictracker.user.helpers import (
    load_users_from_json,
    save_users_to_json,
    prompt_to_confirm,
    users_to_str,
    user_updates_to_str,
)
from clinictracker.core import run, print_error, TEST_MSG
from clinictracker.utils import construct_content
from clinictracker.user.db_manager import UserServiceDB
from clinictracker.user.email_service import EmailParams, EmailService


DRYRUN_BEGIN_MSG = f"{Color.GREEN}*** DRY RUN BEGIN ***{Color.END}"
DRYRUN_END_MSG = f"{Color.GREEN}*** DRY RUN END ***{Color.END}"
DRYRUN_SEQ_MSG = "User id sequence increment keeps after dry run of insertion."
CREATION_ONLY_MSG = "*** Creation only (data fetching skipped) ***"
CRUD_ONLY_MSG = "*** CRUD only (data fetching skipped) ***"
SKIP_CREATION_MSG = "'--skip-creation' selected. Table creation skipped."


class UserService:
    ABORT_MSG = "Operation cancelled."
    CAUTION_FLG = f"{Color.BOLD}{Color.YELLOW}**CAUTION**{Color.END} "
    USER_COUNT_MSG = "Total users in database: %d"

    def __init__(
        self,
        db: UserServiceDB,
        config: ServiceConfig,
        logger: Logger | MyLogger = getLogger(),
    ) -> None:
        self.db: UserServiceDB = db
        self.config: ServiceConfig = config
        self.logger: Logger | MyLogger = logger
        self.users: list[User] = []
        self.data_all: dict[str, ListData] = {}
        self.city_set: set = set()
        self.max_days_back: int = DAYS_BACK_MIN
        self.max_nmax: int = MAX_ITEMS_MIN
        self.tables_ready: bool = False
        # Create tables
        if config.skip_creation:
            logger.info(SKIP_CREATION_MSG)
        else:
            _created = db.create_users_table()
            self.tables_ready = db.create_sent_items_table() and _created

    def set_params_for_all(self) -> None:
        """Sets `city_set`, `max_days_back`, and `max_nmax` for
        fetching full lists in all cities requested from users.
        """
        if not self.users:
            self.logger.info("No users. Nothing to do.")
            return

        _cities: list[str] = []
        for user in self.users:
            _cities.extend(user.cities)

        max_user_period = max(user.period for user in self.users)
        max_user_nmax = max(user.nmax for user in self.users)

        self.city_set = set(_cities)
        self.max_days_back = max(DAYS_BACK_MIN, max_user_period + 1)
        self.max_nmax = max(MAX_ITEMS_MIN, max_user_nmax)

        self.logger.debug(
            f"max_days_back={self.max_days_back}, max_nmax={self.max_nmax}"
        )
        self.logger.info(f"Cities to check: {', '.join(self.city_set)}")

    def set_params_for_each(self, city: str) -> QueryParams:
        """Sets query parameters for fetching full list for each city."""
        query_dict = {'only_accepting': 'yes', 'list_town': city}
        full_url = get_full_url(self.config.url, '?', query_dict)
        return QueryParams(
            url=full_url,
            city=city,
            days_back=self.max_days_back,
            nmax=self.max_nmax,
            tz=self.config.tz,
        )

    def get_lists_for_all(self) -> None:
        """Fetches data in all cities and sets `data_all`.
        Calls `core.run(query, config, logger, check_date=False)`
        """
        _list_data: ListData
        _data_all: dict[str, ListData] = {}
        for city in self.city_set:
            _query = self.set_params_for_each(city)
            _list_data = run(
                query=_query,
                config=self.config,
                logger=self.logger,
                check_date=False,
            )
            _data_all[city] = _list_data
            if len(_list_data.items) > 0:
                self.logger.info(
                    f"Collected {_list_data.n_tot} items from: {city}"
                )
            else:
                self.logger.info(f"No updates from {city}.")
        self.data_all = _data_all

    def fetch_data_and_send(self) -> None:
        """Fetches full lists of data and send to users."""
        # Fetch data in all cities specified by users
        self.logger.info("Collecting updates for all...")
        self.get_lists_for_all()

        # Process each user
        body_to_send: str
        hashes_to_record: list[str]
        for user in self.users:
            self.logger.info(f"Processing user {user.username}...")
            _res = self.process_user(user)
            body_to_send = _res.get('body')
            hashes_to_record = _res.get('hashes')
            if not body_to_send or not hashes_to_record:
                continue

            # Send email to user
            current_time = datetime.now().astimezone()  # timezone-aware
            es = EmailService(self.logger)

            if not self.config.send:
                es.preview(EmailParams(user, body_to_send))
                continue

            try:
                es.send(EmailParams(user, body_to_send))
            except Exception as e:
                self.logger.error(
                    f"Failed to send email to {user.username}:\n{e}"
                )
                continue
            else:
                self.db.record_sent_items(user, hashes_to_record, current_time)
                self.db.update_last_sent_at(user, current_time)

    def process_user(self, user: User) -> dict[str, str | list[str]]:
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
        if not self.db.should_send_to_user(user, current_time):
            self.logger.info(
                f"Skipping {username}: Not enough time passed since last send."
            )
            return {'body': body_to_send, 'hashes': hashes_to_record}

        unsent_items: list[ItemData]
        email_body_list: list[str] = []
        for city in user.cities:
            self.logger.info(f"Filtering updates in {city} for {username}...")
            unsent_items = []
            _n_tot = self.data_all[city].n_tot
            _query = self.data_all[city].query
            _items = self.data_all[city].items
            _hashes = [item.digest for item in _items]

            if not _items:
                self.logger.info("No updates found.")
                continue

            # Check which items in this city have already been sent
            sent_hashes: set[str] = self.db.get_sent_item_hashes(
                user.id, _hashes
            )
            self.logger.debug(
                f"Found {len(sent_hashes)} updates of {city} "
                f"have been sent to {username}."
            )

            # Get unsent items in this city and limit to nmax
            for item in _items:
                if item.digest not in sent_hashes:
                    unsent_items.append(item)

            items_to_send = unsent_items[:nmax]
            hashes_to_record.extend([item.digest for item in items_to_send])

            if items_to_send:
                email_body_list.append(
                    construct_content(items_to_send, _n_tot, _query, False)
                )
                self.logger.debug(
                    f"About to send {len(items_to_send)} new updates of "
                    f"{city} to {username} (at most {nmax} items)."
                )
            else:
                self.logger.debug(
                    f"No unsent updates in {city} for {username}."
                )
                continue

        if email_body_list:
            body_to_send = '\n'.join(email_body_list)
        else:
            self.logger.info(f"No updates for {username}.")

        return {'body': body_to_send, 'hashes': hashes_to_record}

    def upsert_users(self, users_src: list[User]) -> list[User] | None:
        """Updates and inserts users into database from a list of objects."""
        self.logger.info(
            f"Inserting/Updating {len(users_src)} users into database..."
        )
        if self.config.dryrun:
            self.logger.warning(DRYRUN_SEQ_MSG)
        self.db.insert_users(users_src, update=True)

        if self.config.delete_users:
            # Retrieve all current users in database
            users_db: list[User] = self.db.get_all_users()
            self.logger.info(self.USER_COUNT_MSG % len(users_db))
            if not users_db:
                return users_db

            _username_set_src = {user.username for user in users_src}
            _username_set_db = {user.username for user in users_db}
            _username_diff = _username_set_db - _username_set_src
            if len(_username_diff) > 0:
                if prompt_to_confirm(
                    f"{self.CAUTION_FLG}About to delete users in database that"
                    f" are not in the JSON file: {', '.join(_username_diff)}"
                ):
                    self.logger.info(
                        f"Deleting {len(_username_diff)} users in database..."
                    )
                    for username in _username_diff:
                        self.db.delete_user(username)
                    # Get the current row count
                    count = self.db.get_row_count('users')
                    self.logger.info(self.USER_COUNT_MSG % count)
                    users_db = None  # reset it to retrieve again later
                else:
                    self.logger.info(self.ABORT_MSG)
            return users_db

        return None

    def get_users(self, usernames: list[str] | None) -> list[User]:
        """Retrieves users from database."""
        users_db: list[User] = []
        if usernames is None:
            users_db = self.db.get_all_users()
            self.logger.info(self.USER_COUNT_MSG % len(users_db))
        else:
            # Retrieve specified users in database
            for username in usernames:
                _user = self.db.get_user_by_username(username)
                if _user is not None:
                    users_db.append(_user)
                else:
                    self.logger.warning(self.db.USER_NOT_FOUND_MSG % username)
            self.logger.info(f"Retrieved {len(users_db)} users.")
        return users_db

    def add_users(self, users: list[User]) -> None:
        """Inserts users to database."""
        self.logger.info(f"Inserting {len(users)} users into database...")
        if self.config.dryrun:
            self.logger.warning(DRYRUN_SEQ_MSG)
        self.db.insert_users(users)

    def update_users(self, updates_list: list[dict[str, Any]]) -> None:
        """Updates users in database from dicts."""
        self.logger.info(f"Updating {len(updates_list)} users in database...")
        for updates in updates_list:
            _username = updates.pop('username')
            _user_db = self.db.get_user_by_username(_username)
            if _user_db is not None:
                if prompt_to_confirm(
                    f"About to update user:\n"
                    f"{user_updates_to_str(_user_db, updates)}"
                ):
                    self.logger.info(f"Updating {_username} in database...")
                    self.db.update_user(_username, updates)
                else:
                    self.logger.info(self.ABORT_MSG)
            else:
                self.logger.warning(self.db.USER_NOT_FOUND_MSG % _username)

    def delete_users(self, usernames: list[str]) -> None:
        """Deletes specified users in database."""
        for username in usernames:
            _user_db = self.db.get_user_by_username(username)
            if _user_db is not None:
                if prompt_to_confirm(f"About to delete user:\n{_user_db!s}"):
                    self.logger.info(f"Deleting {username} in database...")
                    self.db.delete_user(username)
                else:
                    self.logger.info(self.ABORT_MSG)
            else:
                self.logger.warning(self.db.USER_NOT_FOUND_MSG % username)

    def reset_seq(self) -> None:
        """Resets user id sequence in database."""
        if prompt_to_confirm(
            f"{self.CAUTION_FLG}About to reset user id sequence in database"
        ):
            self.logger.info("Resetting user id sequence...")
            self.db.reset_id_seq()
        else:
            self.logger.info(self.ABORT_MSG)

    def clear_tables(self, tables: list[str]) -> None:
        """Clears specified tables in database."""
        for tb in tables:
            cascade = True if tb == 'users' else False
            if prompt_to_confirm(
                f"{self.CAUTION_FLG}About to remove all rows from "
                f"table: {tb} (cascade={cascade})"
            ):
                self.logger.info(f"Truncating {tb} in database...")
                self.db.truncate_table(tb, cascade=cascade)
            else:
                self.logger.info(self.ABORT_MSG)

    def crud_and_get_users(self) -> None:
        """Performs CRUD operations then retrieves all users in database.
        Sets `users`.
        - If `config.load_users` is `True`, overrides
        add/update/delete/clear commands.
        - If `config.load_users` is `True` and `config.delete_users` is `True`,
        delete the users in database that are not in the JSON file.
        """
        users_db: list[User] | None = None
        fetch_all: bool = True
        print_users: bool = False

        # Load data from JSON file and insert/update into database
        users_src: list[User] = []
        if self.config.load_users:
            self.logger.info("Loading data from JSON...")
            users_src = load_users_from_json(
                self.config.json_path, self.logger
            )
            if users_src:
                users_db = self.upsert_users(users_src)
                if users_db is not None:  # already fetched
                    fetch_all = False
            else:
                self.logger.info("Skipping updating users in database...")

        # Handle commands
        if self.config.command is not None:
            fetch_all = False
            match self.config.command.name:
                case CommandName.LIST:
                    if self.config.load_users and self.config.dryrun:
                        # Clear it so won't print
                        users_db = None
                    else:
                        users_db = self.get_users(
                            usernames=self.config.command.data
                        )
                        # Print users_db later
                        print_users = True
                case CommandName.ADD:
                    if not self.config.load_users:
                        # Users in config.command.data are validated
                        _count = self.db.get_row_count('users')
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.add_users(users=self.config.command.data)
                case CommandName.UPD:
                    if not self.config.load_users:
                        # Users in config.command.data are validated
                        _count = self.db.get_row_count('users')
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.update_users(
                            updates_list=self.config.command.data
                        )
                case CommandName.DEL:
                    if not self.config.load_users:
                        _count = self.db.get_row_count('users')
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.delete_users(usernames=self.config.command.data)
                case CommandName.RESET:
                    _count = self.db.get_row_count('users')
                    self.logger.info(self.USER_COUNT_MSG % _count)
                    self.reset_seq()
                case CommandName.CLEAR:
                    if not self.config.load_users:
                        _count = self.db.get_row_count('users')
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.clear_tables(tables=self.config.command.data)
                case _:
                    raise ValueError(
                        f"Unknown command: {self.config.command.name}\n"
                        + "Valid commands: "
                        + ', '.join(name for name in CommandName)
                    )

        # Retrieve all users after operations
        if self.config.save_users or fetch_all:
            users_db = self.db.get_all_users()
            self.logger.info(self.USER_COUNT_MSG % len(users_db))

        # Print users in database
        if users_db:
            self.users = users_db
            if print_users:
                self.logger.info("Users retrieved:\n" + users_to_str(users_db))
            else:
                self.logger.debug("All users:\n" + users_to_str(users_db))


def run_service(
    config: ServiceConfig, logger: Logger | MyLogger = getLogger()
) -> None:
    """Manages user data in the database and process daily updates."""
    if config.dryrun:
        logger.info(DRYRUN_BEGIN_MSG)

    # Initialize database
    with UserServiceDB(dryrun=config.dryrun, logger=logger) as db:
        try:
            if config.test:
                logger.info(TEST_MSG)
                return

            # Initialize & create tables ------------------------------|
            us = UserService(db, config, logger)

            if config.creation_only:
                logger.info(CREATION_ONLY_MSG)
                return

            if not us.tables_ready:
                return

            # Perform CRUD operations and retrieve all users ----------|
            us.crud_and_get_users()

            if config.crud_only:
                logger.info(CRUD_ONLY_MSG)
                return

            if config.dryrun:
                return

            # Go fetch and send data ----------------------------------|
            if config.command is None:
                if not us.users:
                    logger.info("No users. Nothing to do.")
                    return

                # Set query parameters based on all users
                us.set_params_for_all()

                # Prepare data and send to all users
                us.fetch_data_and_send()
                current_time = datetime.now().astimezone()  # timezone-aware

                # Cleanup old records
                _stale_days = us.max_days_back + CLEANUP_BUFFER_DAYS
                logger.info(
                    "Cleaning up sent_items records more than "
                    f"{_stale_days} days old..."
                )
                cutoff_date = current_time - timedelta(days=_stale_days)
                db.cleanup_old_sent_items(cutoff_date)
                _count = db.get_row_count('sent_items')
                logger.info(f"Current sent records: {_count}")

            # Save User objects to JSON -------------------------------|
            if config.save_users:
                logger.info("Saving users to file...")
                save_users_to_json(us.users, config.json_path, logger)

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

        finally:
            if config.dryrun:
                logger.info(DRYRUN_END_MSG)
