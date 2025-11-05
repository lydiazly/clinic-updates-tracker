# -*- coding: utf-8 -*-
# user/user_service.py
"""User service."""

import asyncio
from datetime import datetime, timedelta
from logging import Logger, getLogger
from playwright.async_api import TimeoutError
import traceback
from typing import TypedDict, cast

from clinictracker.models import ItemData, ListData
from clinictracker.user.models import User, UserDict
from clinictracker.user.config import (
    CommandName,
    ServiceConfig,
    ServiceName,
    TableName,
    DAYS_BACK_MIN,
    MAX_ITEMS_MIN,
    CLEANUP_BUFFER_DAYS,
    PGSERVICE,
)
from clinictracker.startup import MyLogger, Color, QueryParams, get_full_url
from clinictracker.user.helpers import (
    load_users_from_json,
    save_users_to_json,
    prompt_to_confirm,
    users_to_str,
    user_updates_to_str,
)
from clinictracker.core import run, TEST_MSG
from clinictracker.utils import print_error, construct_content
from clinictracker.user.db_manager import UserServiceDB
from clinictracker.user.email_service import EmailParams, EmailService


DRYRUN_BEGIN_MSG = f"{Color.GREEN}*** DRY RUN BEGIN ***{Color.END}"
DRYRUN_END_MSG = f"{Color.GREEN}*** DRY RUN END ***{Color.END}"
DRYRUN_SEQ_MSG = "User id sequence increment keeps after dry run of insertion."
CREATE_ONLY_MSG = "*** Create only (data fetching skipped) ***"
CRUD_ONLY_MSG = "*** CRUD only (data fetching skipped) ***"
SKIP_CREATION_MSG = "'--skip-creation' selected. Table creation skipped."


class UserService:
    ABORT_MSG = "Operation cancelled."
    CAUTION_FLG = f"{Color.BOLD}{Color.YELLOW}**CAUTION**{Color.END} "
    USER_COUNT_MSG = "Total users in database: %d"
    # Type alias
    _CitiesDataType = dict[str, ListData]

    class _ContentToSend(TypedDict):
        body: str
        hashes: list[str]

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
        self.selected_users: list[User] = []
        self.cities_data: UserService._CitiesDataType = {}
        self.city_set: set[str] = set()
        self.max_days_back: int = DAYS_BACK_MIN
        self.max_nmax: int = MAX_ITEMS_MIN
        self.tables_ready: bool = False
        # Create tables
        if config.skip_creation:
            logger.info(SKIP_CREATION_MSG)
        else:
            _created = db.create_users_table()
            self.tables_ready = _created and db.create_sent_items_table()

    def select_users(self) -> None:
        """Selects users to serve. Sets `selected_users`."""
        usernames: list[str] | None = self.config.usernames

        if self.config.ignore_hash:
            if usernames is None:
                self.selected_users = self.users
            else:
                self.selected_users = [
                    u for u in self.users if u.username in usernames
                ]
        else:
            # Check if enough time has passed since last_sent_at
            current_time = datetime.now().astimezone()  # timezone-aware
            _users: list[User] = []
            for user in self.users:
                if usernames is None or user.username in usernames:
                    if self.db.should_send_to_user(user, current_time):
                        _users.append(user)
                    else:
                        self.logger.info(
                            f"Skipping {user.username}: Not enough time "
                            "passed since last send"
                        )
            self.selected_users = _users
        self.logger.debug(
            "Specified users: " + ', '.join(usernames) if usernames else 'all'
        )
        self.logger.debug(
            "Users to serve: "
            + ', '.join(u.username for u in self.selected_users)
        )

    def set_params_for_all(self) -> bool:
        """Sets `city_set`, `max_days_back`, and `max_nmax` for
        fetching full lists in all cities requested from selected users.
        Returns `True` if succeed.
        """
        if not self.selected_users:
            self.logger.info("No users to serve. Nothing to do.")
            return False

        _cities: list[str] = []
        for user in self.selected_users:
            _cities.extend(user.cities)

        max_user_period = max(user.period for user in self.selected_users)
        max_user_nmax = max(user.nmax for user in self.selected_users)

        self.city_set = set(_cities)
        self.max_days_back = max(DAYS_BACK_MIN, max_user_period + 1)
        self.max_nmax = max(MAX_ITEMS_MIN, max_user_nmax)

        self.logger.debug(
            f"max_days_back={self.max_days_back}, max_nmax={self.max_nmax}"
        )
        self.logger.info(f"Cities to check: {', '.join(self.city_set)}")

        return True

    def set_params_for_each(self, city: str) -> QueryParams:
        """Sets query parameters for fetching full list for each city."""
        query_dict = {'only_accepting': 'yes', 'list_town': city}
        full_url = get_full_url(self.config.url, query_dict)
        return QueryParams(
            url=full_url,
            city=city,
            days_back=self.max_days_back,
            nmax=self.max_nmax,
            tz=self.config.tz,
        )

    def upsert_users(self, users_src: list[User]) -> list[User] | None:
        """Updates and inserts users into database from a list of objects."""
        self.logger.info(
            f"Inserting/Updating {len(users_src)} users into database..."
        )
        if self.config.dryrun:
            self.logger.warning(DRYRUN_SEQ_MSG)
        self.db.insert_users(users_src, update=True)

        users_db: list[User] | None
        if self.config.delete_users:
            # Retrieve all current users in database
            users_db = self.db.get_all_users()
            self.logger.info(self.USER_COUNT_MSG % len(users_db))
            if not users_db:
                return users_db

            _username_set_src = {user.username for user in users_src}
            _username_set_db = {user.username for user in users_db}
            _username_diff = _username_set_db - _username_set_src
            if (_diff_len := len(_username_diff)) > 0:
                if prompt_to_confirm(
                    f"{self.CAUTION_FLG}About to delete users in database that"
                    f" are not in the JSON file: {', '.join(_username_diff)}"
                ):
                    self.logger.info(
                        f"Deleting {_diff_len} users in database..."
                    )
                    for username in _username_diff:
                        self.db.delete_user(username)
                    # Get the current row count
                    count = self.db.get_row_count(TableName.USERS)
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

    def update_users(self, updates_list: list[UserDict]) -> None:
        """Updates users in database from dicts."""
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

    def clear_tables(self, tables: list[TableName]) -> None:
        """Clears specified tables in database."""
        for tb in tables:
            cascade = True if tb == TableName.USERS else False
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
        if self.config.load_users:
            self.logger.info("Loading data from JSON...")
            users_src: list[User] = load_users_from_json(
                self.config.json_path, self.logger
            )
            if users_src:
                users_db = self.upsert_users(users_src)
                if users_db is not None:  # won't fetch again
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
                            usernames=cast(
                                list[str] | None, self.config.command.data
                            )
                        )
                        # Print users_db later
                        print_users = True
                case CommandName.ADD:
                    if not self.config.load_users:
                        # Users in config.command.data are validated
                        _count = self.db.get_row_count(TableName.USERS)
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.add_users(
                            users=cast(list[User], self.config.command.data)
                        )
                case CommandName.UPD:
                    if not self.config.load_users:
                        # Users in config.command.data are validated
                        _count = self.db.get_row_count(TableName.USERS)
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.update_users(
                            updates_list=cast(
                                list[UserDict], self.config.command.data
                            )
                        )
                case CommandName.DEL:
                    if not self.config.load_users:
                        _count = self.db.get_row_count(TableName.USERS)
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.delete_users(
                            usernames=cast(list[str], self.config.command.data)
                        )
                case CommandName.RESET:
                    _count = self.db.get_row_count(TableName.USERS)
                    self.logger.info(self.USER_COUNT_MSG % _count)
                    self.reset_seq()
                case CommandName.CLEAR:
                    if not self.config.load_users:
                        _count = self.db.get_row_count(TableName.USERS)
                        self.logger.info(self.USER_COUNT_MSG % _count)
                        self.clear_tables(
                            cast(list[TableName], self.config.command.data)
                        )
                case _:
                    raise RuntimeError(
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

    async def get_lists_for_all(self) -> None:
        """Fetches data in all cities and sets `cities_data`.
        Calls `core.run(query, config, logger, check_date=False)`
        """
        _cities: list[str] = list(self.city_set)
        _cities_data: UserService._CitiesDataType = {}
        _queries: list[QueryParams] = [
            self.set_params_for_each(city) for city in _cities
        ]

        _data_all: list[ListData] | None = None
        for i in range(0, self.config.retries + 1):
            try:
                _data_all = await run(
                    queries=_queries,
                    config=self.config,
                    logger=self.logger,
                    check_date=False,
                )
            except TimeoutError:
                if i == self.config.retries:
                    raise
                self.logger.info(
                    f"Waiting to retry ({i + 1}/{self.config.retries})..."
                )
                await asyncio.sleep(5)
            except Exception:
                raise
            else:
                break

        if _data_all is None:
            self.logger.warning("Data not fetched.")
            return

        for i, city in enumerate(_cities):
            if len(_data_all[i].items) > 0:
                _cities_data[city] = _data_all[i]
            else:
                self.logger.info(f"No updates from {city}.")
        self.cities_data = _cities_data
        self.logger.info("Updates from all cities are ready.")

    async def fetch_data_and_send(self, es: EmailService) -> bool:
        """Fetches full lists of data and send to selected users."""
        # Determine the users to serve
        self.select_users()

        # Set query parameters based on all users
        _params_ready: bool = self.set_params_for_all()
        if not _params_ready:
            return False

        # Fetch data in all cities specified by selected users
        self.logger.info("Collecting updates for all...")
        await self.get_lists_for_all()

        if not self.cities_data:
            return False

        # Process each user
        body_to_send: str
        hashes_to_record: list[str]
        _content_to_send: UserService._ContentToSend
        success: bool = True
        for user in self.selected_users:
            self.logger.info(f"Processing user {user.username}...")
            _content_to_send = self.process_user(user)
            body_to_send = _content_to_send.get('body', '')
            hashes_to_record = _content_to_send.get('hashes', [])
            if not body_to_send or not hashes_to_record:
                continue

            # Print email content for this user
            if not self.config.send:
                es.preview(EmailParams(user, body_to_send))
                continue

            # Send email to this user
            try:
                es.send(EmailParams(user, body_to_send))
            except Exception as e:
                print_error(e, self.logger)
                success = False
                continue
            else:
                current_time = datetime.now().astimezone()  # timezone-aware
                self.db.record_sent_items(user, hashes_to_record, current_time)
                self.db.update_last_sent_at(user, current_time)

        if success:
            if self.config.send:
                self.logger.info("✓ All emails sent successfully.")
                return True
            else:
                return False
        else:
            raise RuntimeError("Error during email sending.")

    def process_user(self, user: User) -> _ContentToSend:
        """Filters data for a user and constructs the email body.
        Items are filtered by hash values instead of dates.

        Returns:
            content_to_send: A dict with keys:
                body (str): Email body to send to the user
                hashes (list[str]): List of item hash values to be sent
        """
        body_to_send: str = ''
        hashes_to_record: list[str] = []
        username: str = user.username
        nmax: int = user.nmax

        _email_body_list: list[str] = []
        _unsent_items: list[ItemData]
        for city in user.cities:
            if city not in self.cities_data or not (
                _items := self.cities_data[city].items
            ):
                continue

            # Check which items in this city have already been sent
            self.logger.info(f"Filtering updates in {city} for {username}...")
            _unsent_items = []
            _n_tot = self.cities_data[city].n_tot
            _query = self.cities_data[city].query
            _hashes = [item.digest for item in _items]
            _sent_hashes: set[str] = set()
            if not self.config.ignore_hash:
                _sent_hashes = self.db.get_sent_item_hashes(user.id, _hashes)
                self.logger.debug(
                    f"Found {len(_sent_hashes)} updates of {city} "
                    f"have been sent to {username}."
                )
            else:
                self.logger.debug(
                    "'--ignore-hash' selected. Skipping sent items checking..."
                )

            # Get unsent items in this city and limit to nmax
            for item in _items:
                if item.digest not in _sent_hashes:
                    _unsent_items.append(item)

            items_to_send = _unsent_items[:nmax]
            hashes_to_record.extend([item.digest for item in items_to_send])

            if items_to_send:
                _email_body_list.append(
                    construct_content(items_to_send, _n_tot, _query, False)
                )
                self.logger.debug(
                    f"About to send {len(items_to_send)} new updates of "
                    f"{city} to {username} (at most {nmax} items)."
                )
            else:
                self.logger.debug(
                    f"No unsent new updates in {city} for {username}."
                )
                continue

        if _email_body_list:
            body_to_send = '\n'.join(_email_body_list)
        else:
            self.logger.info(f"No updates for {username}.")

        return {'body': body_to_send, 'hashes': hashes_to_record}


async def run_service(
    config: ServiceConfig, logger: Logger | MyLogger = getLogger()
) -> None:
    """Manages user data in the database and process daily updates."""
    if config.dryrun:
        logger.info(DRYRUN_BEGIN_MSG)

    try:
        # Initialize database -----------------------------------------|
        with UserServiceDB(
            service_name=ServiceName(PGSERVICE),
            dryrun=config.dryrun,
            logger=logger,
        ) as db:
            if config.test:
                logger.info(TEST_MSG)
                return

            # Initialize & create tables ------------------------------|
            us = UserService(db, config, logger)

            if config.create_only:
                logger.info(CREATE_ONLY_MSG)
                return

            if not us.tables_ready:
                return

            # Perform CRUD operations and retrieve all users ----------|
            us.crud_and_get_users()

            # Go fetch and send data ----------------------------------|
            if (
                not config.dryrun
                and not config.crud_only
                and config.command is None
            ):
                # Initialize email service
                es = EmailService(logger)

                # Prepare data and send to all users
                is_sent: bool = await us.fetch_data_and_send(es)

                if is_sent:
                    # Cleanup old records
                    _stale_days = us.max_days_back + CLEANUP_BUFFER_DAYS
                    logger.info(
                        f"Removing records more than {_stale_days} days old..."
                    )
                    current_time = datetime.now().astimezone()
                    cutoff_date = current_time - timedelta(days=_stale_days)
                    db.cleanup_old_sent_items(cutoff_date)
                    _count = db.get_row_count(TableName.SENT)
                    logger.info(f"Current sent records: {_count}")

            # Save User objects to JSON -------------------------------|
            if config.save_users:
                logger.info("Saving users to file...")
                save_users_to_json(us.users, config.json_path, logger)

            if config.crud_only:
                logger.info(CRUD_ONLY_MSG)
                return

            if config.dryrun:
                return

    except TimeoutError:
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

    finally:
        if config.dryrun:
            logger.info(DRYRUN_END_MSG)
