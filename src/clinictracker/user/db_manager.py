# -*- coding: utf-8 -*-
# user/db_manager.py
"""PostSQL database manager."""

import asyncio
from dataclasses import fields
from datetime import datetime, timedelta
from logging import Logger
import os
from pathlib import Path
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
from textwrap import dedent
from types import TracebackType
from typing import Self, Literal, cast

from clinictracker.user.models import (
    User,
    UserDict,
    ALLOWED_COLS,
)
from clinictracker.user.config import (
    PGSERVICE_PATH,
    PGPASS_PATH,
    ServiceName,
    TableName,
)
from clinictracker.startup import MyLogger, default_logger
from clinictracker.user.helpers import (
    get_valid_user,
    validate_user_field,
    ensure_pgpass_match,
)


class UserServiceDB:
    PERIOD_BUFFER: timedelta = timedelta(minutes=30)
    CONNECT_MSG = "Connected to PostgreSQL database."
    CLOSED_MSG = "Database connection closed."
    CHECK_TABLE_QUERY = dedent(
        """
        SELECT EXISTS (
            SELECT FROM pg_catalog.pg_tables
            WHERE schemaname = 'public' AND tablename = %s
        );
        """
    )
    TABLE_CHECK_ERR = "Unable to check table: %s"
    TABLE_EXIST_MSG = "Table '%s' already exists. Skipping creation..."
    TABLE_CREATE_MSG = "Table created: %s"
    TABLE_CREATE_ERR = "Unable to create table: %s"
    TABLE_CLEAR_MSG = "Removed all rows from: %s"
    USER_NOT_FOUND_MSG = "User not found: %s. Skipping..."
    USER_EXIST_MSG = "User already exists: %s. Skipping..."
    SEQ_NOT_FOUND_MSG = "Sequence not found: users_id_seq"

    def __init__(
        self,
        service_name: ServiceName = ServiceName.DEV_LOCAL,
        dryrun: bool = False,
        logger: Logger | MyLogger = default_logger,
    ) -> None:
        self.service_name: ServiceName = service_name
        self.dryrun: bool = dryrun
        self.logger: Logger | MyLogger = logger
        self.conn: psycopg2.extensions.connection | None = None
        self.cur: psycopg2.extensions.cursor | None = None

    def __enter__(self) -> Self:
        self._check_service_and_password()
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_type is not None and exc_type is not asyncio.CancelledError:
            self.logger.error("Error during operations.")
        try:
            self.close()
        except Exception as e:
            self.logger.error(f"Error during disconnection: {e}")
            raise
        return False

    def _ensure_connected(
        self,
    ) -> tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor]:
        if self.conn is None or self.cur is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self.conn, self.cur

    def _check_service_and_password(self) -> None:
        """Sets environment variables `PGSERVICEFILE` and `PGPASSFILE`."""
        if not PGSERVICE_PATH.is_file():
            raise RuntimeError(
                f"Service file not found: {PGSERVICE_PATH}. "
                "Set $PGSERVICEFILE to the service file path."
            )
        if not PGPASS_PATH.is_file():
            raise RuntimeError(
                f"Password file not found: {PGPASS_PATH}. "
                "Set $PGPASSFILE to the password file path."
            )
        # Tell libpq where to find the service and password file
        os.environ['PGSERVICEFILE'] = str(PGSERVICE_PATH.resolve())
        os.environ['PGPASSFILE'] = str(PGPASS_PATH.resolve())
        # To verify, load again from environment variables
        service_path: Path = Path(os.getenv('PGSERVICEFILE', 'void'))
        pgpass_path: Path = Path(os.getenv('PGPASSFILE', 'void'))
        _perm = oct(pgpass_path.stat().st_mode)[-3:]
        self.logger.debug(f"PGSERVICEFILE: {service_path}")
        self.logger.debug(f"PGPASSFILE: {pgpass_path} (perm: {_perm})")

        # Check file permissions (should be 0600)
        if _perm != '600':
            raise RuntimeError(
                "Password file has incorrect permissions. Should be 0600."
            )

        # Ensure service matching an entry in pgpass
        ensure_pgpass_match(self.service_name.value, service_path, pgpass_path)

    def _print_conn_params(self) -> None:
        conn, cur = self._ensure_connected()
        _conn_params: dict[str, str] = conn.get_dsn_parameters()
        self.logger.debug(
            '\n'.join(
                [
                    "Connection parameters:",
                    f"Host: {_conn_params.get('host')}",
                    f"Port: {_conn_params.get('port')}",
                    f"Database: {_conn_params.get('dbname')}",
                    f"User: {_conn_params.get('user')}",
                ]
            )
        )

    def connect(self) -> None:
        """Establishes database connection."""
        try:
            # libpq will automatically read $PGSERVICEFILE and $PGPASSFILE
            self.conn = psycopg2.connect(service=self.service_name)
            self.cur = self.conn.cursor()
        except Exception as e:
            raise RuntimeError("Error connecting to database.") from e
        else:
            self.logger.info(self.CONNECT_MSG)
            self._print_conn_params()

    def close(self) -> None:
        """Closes database connection."""
        _errors = []

        if self.cur is not None:
            try:
                self.cur.close()
            except Exception as e:
                _errors.append(f"(cursor) {type(e).__name__}: {e}")
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception as e:
                _errors.append(f"(connection) {type(e).__name__}: {e}")

        if _errors:
            _errors_all = '\n'.join(_errors)
            raise RuntimeError(f"Error closing connection:\n{_errors_all}")
        else:
            self.logger.info(self.CLOSED_MSG)

    def tables_exist(self, *table_names: TableName) -> bool:
        """Checks if tables exist."""
        conn, cur = self._ensure_connected()

        for table_name in table_names:
            try:
                cur.execute(self.CHECK_TABLE_QUERY, (table_name,))
            except Exception as e:
                raise RuntimeError(self.TABLE_CHECK_ERR % table_name) from e
            row = cur.fetchone()
            if not row or not row[0]:
                return False

        return True

    def create_users_table(self) -> bool:
        """Creates "users" table. Returns `True` if created.
        - Columns: id, username, nickname, emails, cities, period, nmax,
                   last_sent_at, created_at, updated_at
        - Primary key: id
        """
        conn, cur = self._ensure_connected()

        if self.tables_exist(TableName.USERS):
            self.logger.info(self.TABLE_EXIST_MSG % TableName.USERS)
            return True

        query = dedent(
            """
            -- 1. Create columns with default values
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                nickname VARCHAR(30),
                emails VARCHAR(50)[] NOT NULL CHECK (array_length(emails, 1) >= 1),
                cities VARCHAR(50)[] NOT NULL CHECK (array_length(cities, 1) >= 1),
                period INTEGER DEFAULT 1 CHECK (period > 0),
                nmax INTEGER DEFAULT 10 CHECK (nmax > 0),
                last_sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            -- 2. Create a trigger function (once per database)
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            -- 3. Create the trigger on the table
            CREATE TRIGGER update_users_updated_at
                BEFORE UPDATE ON users
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
            """
        )
        try:
            cur.execute(query)
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(self.TABLE_CREATE_ERR % TableName.USERS) from e
        else:
            self.logger.info(self.TABLE_CREATE_MSG % TableName.USERS)
            return not self.dryrun

    def create_sent_items_table(self) -> bool:
        """Creates "sent_items" table for tracking sent items per user.
        Returns `True` if created.
        - Columns: user_id, item_hash, sent_at
        - Primary key: (user_id, item_hash)
        - Foreign key: user_id references users(id)
        """
        conn, cur = self._ensure_connected()

        if self.tables_exist(TableName.SENT):
            self.logger.info(self.TABLE_EXIST_MSG % TableName.SENT)
            return True

        query = dedent(
            """
            CREATE TABLE IF NOT EXISTS sent_items (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                item_hash VARCHAR(64) NOT NULL,
                sent_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (user_id, item_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_sent_items_hash ON sent_items(item_hash);
            CREATE INDEX IF NOT EXISTS idx_sent_items_sent_at ON sent_items(sent_at);
            """
        )
        try:
            cur.execute(query)
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(self.TABLE_CREATE_ERR % TableName.SENT) from e
        else:
            self.logger.info(self.TABLE_CREATE_MSG % TableName.SENT)
            return not self.dryrun

    def insert_users(self, users: list[User], update: bool = False) -> bool:
        """Inserts/Updates `User` objects into database and increment
        sequence only after inserting new rows.
        If `update=False`, insert only.
        Returns `True` if inserted new entries.
        """
        conn, cur = self._ensure_connected()

        # Though may have been validated before, validate again
        validated_users: list[User] = []
        for user in users:
            try:
                validated_user = get_valid_user(user)
                validated_users.append(validated_user)
            except ValueError as e:
                self.logger.warning(f"Skipping invalid user: {e}")
                continue
        if not validated_users:
            self.logger.warning("No valid users to insert/update.")
            return False

        values = [
            {field: getattr(user, field) for field in ALLOWED_COLS}
            for user in validated_users
        ]
        update_cols = [col for col in ALLOWED_COLS if col != 'username']

        cols_sql = sql.SQL(', ').join(map(sql.Identifier, ALLOWED_COLS))
        vals_sql = sql.SQL(', ').join(map(sql.Placeholder, ALLOWED_COLS))
        vals_tmpl = sql.SQL("({})").format(vals_sql).as_string(conn)
        tmp_tb_sql = sql.Identifier('temp_users')
        set_sql = sql.SQL(', ').join(
            sql.SQL("{col} = t.{col}").format(col=sql.Identifier(col))
            for col in update_cols
        )
        tmp_cols_sql = sql.SQL(', ').join(
            sql.SQL("t.{cols}").format(cols=sql.Identifier(col))
            for col in ALLOWED_COLS
        )
        # Create temp table (automatically dropped at session end)
        # (only create selected columns, excluding id)
        tmp_tb_query = sql.SQL(
            dedent(
                """
                CREATE TEMP TABLE {tb} AS
                SELECT {cols}
                FROM users
                WHERE false;  -- no data
                """
            )
        ).format(tb=tmp_tb_sql, cols=cols_sql)
        # Bulk insert into temp table
        insert_query = sql.SQL("INSERT INTO {tb} ({cols}) VALUES %s;").format(
            tb=tmp_tb_sql, cols=cols_sql
        )
        # Update existing rows with selected columns and get updated usernames
        update_from_tmp_query = sql.SQL(
            dedent(
                """
                UPDATE users u
                SET {updates}
                FROM {tb} t
                WHERE u.username = t.username
                RETURNING u.username;
                """
            )
        ).format(tb=tmp_tb_sql, updates=set_sql)
        # Insert only new rows using LEFT JOIN and get inserted usernames
        # (doesn't increment sequence for existing rows)
        insert_from_tmp_query = sql.SQL(
            dedent(
                """
                INSERT INTO users ({cols})
                SELECT {tmp_cols}
                FROM {tb} t
                LEFT JOIN users u ON u.username = t.username
                WHERE u.username IS NULL
                RETURNING username;
                """
            )
        ).format(tb=tmp_tb_sql, cols=cols_sql, tmp_cols=tmp_cols_sql)
        # self.logger.debug(tmp_tb_query.as_string(conn))
        # self.logger.debug(insert_query.as_string(conn))
        # self.logger.debug(upsert_query.as_string(conn))

        updated_usernames: list[str] = []
        inserted_usernames: list[str] = []
        update_count: int = 0
        insert_count: int = 0
        try:
            # Create temp table
            cur.execute(tmp_tb_query)
            # Bulk insert into temp table
            execute_values(cur, insert_query, values, template=vals_tmpl)
            if update:
                # Update from temp table
                cur.execute(update_from_tmp_query)
                updated_usernames = [row[0] for row in cur.fetchall()]
                update_count = cur.rowcount
            # Insert from temp table
            cur.execute(insert_from_tmp_query)
            inserted_usernames = [row[0] for row in cur.fetchall()]
            insert_count = cur.rowcount
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        # except psycopg2.errors.UniqueViolation as e:
        #     conn.rollback()
        #     username = re.search(r'\(username\)=\(([^)]+)\)', str(e))
        #     username = username.group(1) if username else e
        #     self.logger.warning(self.USER_EXIST_MSG % username)
        #     return False
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                f"Unable to insert{'/update' if update else ''} users."
            ) from e
        else:
            if update:
                if update_count > 0:
                    self.logger.info(
                        f"Updated {update_count} users: "
                        + ', '.join(updated_usernames)
                    )
            else:
                # Warn conflicts if insert only
                for user in validated_users:
                    if user.username not in inserted_usernames:
                        self.logger.warning(
                            self.USER_EXIST_MSG % user.username
                        )
            if (has_inserted := insert_count > 0):
                self.logger.info(
                    f"Inserted {insert_count} users: "
                    + ', '.join(inserted_usernames)
                )
            return has_inserted

    def update_user(self, username: str, updates: UserDict) -> None:
        """Validates and updates user fields from a dict."""
        conn, cur = self._ensure_connected()

        # Validate all keys are in the whitelist
        invalid_keys: set[str] = set(updates.keys()) - set(ALLOWED_COLS)
        if invalid_keys:
            raise ValueError(
                f"Unable to update user: {username}\n"
                f"Invalid fields: {invalid_keys}"
            )
        # Validate values
        for k, v in updates.items():
            validate_user_field(username, k, v)

        set_sql = sql.SQL(', ').join(
            sql.SQL("{col} = {val}").format(
                col=sql.Identifier(k), val=sql.Placeholder(k)
            )
            for k in updates.keys()
        )
        query = sql.SQL(
            "UPDATE users SET {updates} WHERE username = %(username)s;"
        ).format(updates=set_sql)
        # self.logger.debug(query.as_string(conn))

        values = updates | {'username': username}

        try:
            cur.execute(query, values)
            if cur.rowcount == 0:
                self.logger.warning(self.USER_NOT_FOUND_MSG % username)
                conn.rollback()
                return
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Unable to update user: {username}") from e
        else:
            self.logger.info(f"Updated user: {username}")

    def delete_user(self, username: str) -> None:
        """Deletes a specific user by username."""
        conn, cur = self._ensure_connected()

        query = "DELETE FROM users WHERE username = %s;"
        try:
            cur.execute(query, (username,))
            if cur.rowcount == 0:
                self.logger.warning(self.USER_NOT_FOUND_MSG % username)
                conn.rollback()
                return
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Unable to delete user: {username}") from e
        else:
            self.logger.info(f"Deleted user: {username}")

    def get_all_usernames(self) -> list[str]:
        """Retrieves all usernames from database."""
        conn, cur = self._ensure_connected()

        query = "SELECT username FROM users ORDER BY id;"

        try:
            cur.execute(query)
        except Exception as e:
            raise RuntimeError("Unable to fetch usernames.") from e
        else:
            return [row[0] for row in cur.fetchall()]

    def get_all_users(self) -> list[User]:
        """Retrieves all users from database."""
        conn, cur = self._ensure_connected()

        field_names = [field.name for field in fields(User)]
        query = sql.SQL("SELECT {cols} FROM users ORDER BY id;").format(
            cols=sql.SQL(', ').join(map(sql.Identifier, field_names))
        )
        # self.logger.debug(query.as_string(conn))

        try:
            cur.execute(query)
        except Exception as e:
            raise RuntimeError("Unable to fetch users.") from e
        else:
            return [User(*row) for row in cur.fetchall()]

    def get_user_by_username(self, username: str) -> User | None:
        """Retrieves a specific user by username."""
        conn, cur = self._ensure_connected()

        field_names = [field.name for field in fields(User)]
        query = sql.SQL(
            "SELECT {cols} FROM users WHERE username = %s;"
        ).format(cols=sql.SQL(', ').join(map(sql.Identifier, field_names)))
        # self.logger.debug(query.as_string(conn))

        try:
            cur.execute(query, (username,))
        except Exception as e:
            raise RuntimeError(f"Unable to fetch user: {username}") from e
        else:
            row = cur.fetchone()
            if row:
                return User(*row)
            return None

    def get_sent_item_hashes(
        self, user_id: int, item_hashes: list[str]
    ) -> set[str]:
        """Returns which item hashes have already been sent to this user."""
        if not item_hashes:
            return set()

        conn, cur = self._ensure_connected()

        query = dedent(
            """
            SELECT item_hash FROM sent_items
            WHERE user_id = %s AND item_hash = ANY(%s);
            """
        )
        try:
            cur.execute(query, (user_id, item_hashes))
        except Exception as e:
            raise RuntimeError("Unable to check hashes.") from e
        else:
            return {row[0] for row in cur.fetchall()}

    @classmethod
    def should_send_to_user(
        cls,
        user: User,
        current_time: datetime,
        buffer: timedelta | None = None,
    ) -> bool:
        """Checks if enough time has passed based on user's period.
        Automatically handles timezone conversion for timezone-aware objects.

        30-minute buffer time before last_sent_at is applied.
        """
        if buffer is None:
            buffer = cls.PERIOD_BUFFER

        # Never sent before, should send
        if user.last_sent_at is None:
            return True
        time_diff = current_time - user.last_sent_at + buffer
        return time_diff.days >= user.period

    def record_sent_items(
        self,
        user: User,
        item_hashes: list[str],
        sent_at: datetime | None = None,
    ) -> None:
        """Inserts records into sent_items table."""
        if not item_hashes:
            return

        conn, cur = self._ensure_connected()

        if sent_at is None:
            sent_at = datetime.now().astimezone()  # timezone-aware

        query = dedent(
            """
            INSERT INTO sent_items (user_id, item_hash, sent_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, item_hash) DO NOTHING;
            """
        )
        values = [(user.id, item_hash, sent_at) for item_hash in item_hashes]
        try:
            cur.executemany(query, values)
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                f"Unable to insert sent hashes for: {user.username}"
            ) from e
        else:
            self.logger.info(f"Recorded {cur.rowcount} new items.")

    def update_last_sent_at(
        self, user: User, sent_at: datetime | None = None
    ) -> None:
        """Updates the user's last_sent_at field."""
        conn, cur = self._ensure_connected()

        if sent_at is None:
            sent_at = datetime.now().astimezone()  # timezone-aware

        query = "UPDATE users SET last_sent_at = %s WHERE id = %s;"
        try:
            cur.execute(query, (sent_at, user.id))
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                f"Unable to update last_sent_at for: {user.username}"
            ) from e
        else:
            self.logger.info(f"Updated last_sent_at for: {user.username}")

    def get_row_count(self, tb: TableName) -> int:
        """Get the row count of a table."""
        conn, cur = self._ensure_connected()

        query = sql.SQL("SELECT COUNT(*) FROM {};").format(sql.Identifier(tb))
        try:
            cur.execute(query)
        except Exception as e:
            raise RuntimeError(f"Unable to get the row count: {tb}") from e
        else:
            row = cur.fetchone()
            if row is not None:
                return cast(int, row[0])
            return 0

    def cleanup_old_sent_items(self, cutoff_date: datetime) -> None:
        """Deletes sent_items records older than the cutoff date."""
        conn, cur = self._ensure_connected()

        query = "DELETE FROM sent_items WHERE sent_at < %s;"
        try:
            cur.execute(query, (cutoff_date,))
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                "Unable to clean up old records in sent_items."
            ) from e
        else:
            self.logger.info(
                f"Cleaned up {cur.rowcount} old records in sent_items."
            )

    def reset_id_seq(self) -> None:
        """Reset sequence 'users_id_seq' to continue from max user id."""
        conn, cur = self._ensure_connected()

        # seq_query = "SELECT pg_get_serial_sequence(TableName.USERS, 'id');"
        reset_query = dedent(
            """
            SELECT setval(
                   'users_id_seq',
                   COALESCE((SELECT MAX(id) FROM users), 0) + 1,
                   false
            );
            """
        )
        value_query = "SELECT last_value, is_called FROM users_id_seq;"
        try:
            # Ensure sequence "users_id_seq" exists and get the name
            # cur.execute(seq_query)
            # row = cur.fetchone()
            # if row is None or row[0] is None:
            #     raise ValueError(self.SEQ_NOT_FOUND_MSG)
            # seq_name = row[0].split('.')[-1]  # remove 'public.'
            # self.logger.debug(f"Sequence name: {seq_name}")
            # Get current value
            # cur.execute(sql.SQL(value_query).format(sql.Identifier(seq_name)))
            cur.execute(value_query)
            _res = cur.fetchone()
            if _res is None:
                raise RuntimeError(self.SEQ_NOT_FOUND_MSG)
            last_value_old, is_called_old = _res
            # Reset to the max user id + 1 (is_called = false)
            # cur.execute(sql.SQL(reset_query).format(sql.Literal(seq_name)))
            cur.execute(reset_query)
            # Check the current value
            # cur.execute(sql.SQL(value_query).format(sql.Identifier(seq_name)))
            cur.execute(value_query)
            last_value_new, is_called_new = cur.fetchone()  # type: ignore[misc]
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError("Unable to reset 'users_id_seq'.") from e
        else:
            next_seq = last_value_new + 1 if is_called_new else last_value_new
            self.logger.debug(
                f"users_id_seq: {last_value_old} (is_called: {is_called_old})"
                f" -> {last_value_new} (is_called: {is_called_new})"
            )
            self.logger.info(f"Reset. Next user id: {next_seq}")

    def truncate_table(
        self,
        table_name: str,
        cascade: bool = False,
        restart_identity: bool = True,
    ) -> None:
        """Truncate (remove all rows from) a table."""
        conn, cur = self._ensure_connected()

        try:
            cur.execute(self.CHECK_TABLE_QUERY, (table_name,))
        except Exception as e:
            raise RuntimeError(self.TABLE_CHECK_ERR % table_name) from e

        row = cur.fetchone()
        if row is None or not row[0]:
            self.logger.info(f"Table not found: {table_name}. Skipping...")
            return

        query = sql.SQL("TRUNCATE TABLE {tb} {restart} {cascade};").format(
            tb=sql.Identifier(table_name),
            restart=sql.SQL(
                "RESTART IDENTITY" if restart_identity else "CONTINUE IDENTITY"
            ),
            cascade=sql.SQL("CASCADE" if cascade else ""),
        )
        try:
            cur.execute(query)
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError("Unable to reset users_id_seq.") from e
        else:
            self.logger.info(f"Table cleared: {table_name} ")


# def initialize_db(
#     pg_password_path: Path = PG_PASSWORD_PATH,
#     dryrun: bool = False,
#     logger: Logger | MyLogger = default_logger,
# ) -> UserServiceDB:
#     """Initialize and connect to the database."""
#     logger.debug(
#         f"Loading password from {PG_PASSWORD_PATH}... "
#         "(set $PG_PASSWORD_PATH to load from another file)"
#     )
#     try:
#         pg_password = pg_password_path.read_text().strip()
#     except Exception as e:
#         logger.debug(f"Unable to load password: {e}")
#         pg_password = getpass("Enter your PostgreSQL password: ")
#     else:
#         logger.debug(f"Loaded password from: {pg_password_path}")
#     db = UserServiceDB(password=pg_password, dryrun=dryrun, logger=logger)
#     return db
