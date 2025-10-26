# -*- coding: utf-8 -*-
# user/db_manager.py
"""PostSQL database manager."""
from dataclasses import fields
from datetime import datetime
from getpass import getpass
from logging import Logger, getLogger
from pathlib import Path
import psycopg2
from psycopg2 import sql
from typing import TypedDict

from clinictracker.user.models import User, ALLOWED_COLS
from clinictracker.startup import MyLogger
from clinictracker.user.helpers import validate_user, validate_user_field


class ConnParams(TypedDict):
    host: str
    port: int
    database: str
    user: str
    password: str


class UserServiceDB:
    CONNECT_MSG = "Connected to PostgreSQL database."
    CLOSED_MSG = "Database connection closed."
    CHECK_TABLE_QUERY = """
    SELECT EXISTS (
        SELECT FROM pg_catalog.pg_tables
        WHERE schemaname = 'public' AND tablename = %s
    );
    """
    TABLE_CHECK_ERR = "Unable to check table: %s"
    TABLE_EXIST_MSG = "Table '%s' already exists. Skipping creation..."
    TABLE_CREATE_MSG = "Table created: %s"
    TABLE_CREATE_ERR = "Unable to create table: %s"
    TABLE_CLEAR_MSG = "Removed all rows from: %s"

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5432,
        database: str = 'userservice',
        user: str = 'admin',
        password: str = '',
        logger: Logger | MyLogger = getLogger(),
    ) -> None:
        self.conn_params: ConnParams = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password,
        }
        self.conn: psycopg2.extensions.connection | None = None
        self.cursor: psycopg2.extensions.cursor | None = None
        self.logger: Logger | MyLogger = logger

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.close()
        except Exception as e:
            # If there was already an exception in the with block, preserve it
            if exc_type is not None:
                # Log the error but don't raise it
                # TODO: test
                self.logger.error(f"Error during operations:\n{e}")
                # Return None/False to let the original exception propagate
                return False
            else:
                # No original exception, so raise the close error
                raise
        # Return None/False to propagate any exception from the with block
        return False

    def _ensure_connected(
        self,
    ) -> tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor]:
        if self.conn is None or self.cursor is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self.conn, self.cursor

    def connect(self) -> None:
        """Establishes database connection."""
        try:
            self.conn = psycopg2.connect(**self.conn_params)
            self.cursor = self.conn.cursor()
        except Exception as e:
            raise RuntimeError("Error connecting to database.") from e
        else:
            self.logger.info(self.CONNECT_MSG)

    def close(self) -> None:
        """Closes database connection."""
        errors = []

        if self.cursor is not None:
            try:
                self.cursor.close()
            except Exception as e:
                errors.append(f"(cursor) {type(e).__name__}: {e}")
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception as e:
                errors.append(f"(connection) {type(e).__name__}: {e}")

        if errors:
            errors_all = '\n'.join(errors)
            raise RuntimeError(
                f"Error closing database connection:\n{errors_all}"
            )
        else:
            self.logger.info(self.CLOSED_MSG)

    def create_users_table(self) -> None:
        """Creates 'users' table.
        - Columns: id, username, nickname, emails, cities, period, nmax,
                   last_sent_at, created_at, updated_at
        - Primary key: id
        """
        conn, cursor = self._ensure_connected()

        try:
            cursor.execute(self.CHECK_TABLE_QUERY, ('users',))
        except Exception as e:
            raise RuntimeError(self.TABLE_CHECK_ERR % 'users') from e

        row = cursor.fetchone()
        if row and row[0]:
            self.logger.info(self.TABLE_EXIST_MSG % 'users')
            return

        create_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            nickname VARCHAR(30),
            emails VARCHAR(50)[] NOT NULL CHECK (array_length(emails, 1) >= 1),
            cities VARCHAR(50)[] NOT NULL CHECK (array_length(cities, 1) >= 1),
            period INTEGER DEFAULT 1 CHECK (period > 0),
            nmax INTEGER DEFAULT 10 CHECK (nmax > 0),
            last_sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        );
        """
        try:
            cursor.execute(create_table_query)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(self.TABLE_CREATE_ERR % 'users') from e
        else:
            self.logger.info(self.TABLE_CREATE_MSG % 'users')

    def create_sent_items_table(self) -> None:
        """Creates 'sent_items' table for tracking sent items per user.
        - Columns: user_id, item_hash, sent_at
        - Primary key: (user_id, item_hash)
        - Foreign key: user_id references users(id)
        """
        conn, cursor = self._ensure_connected()

        try:
            cursor.execute(self.CHECK_TABLE_QUERY, ('sent_items',))
        except Exception as e:
            raise RuntimeError(self.TABLE_CHECK_ERR % 'sent_items') from e

        row = cursor.fetchone()
        if row and row[0]:
            self.logger.info(self.TABLE_EXIST_MSG % 'sent_items')
            return

        create_table_query = """
        CREATE TABLE IF NOT EXISTS sent_items (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_hash VARCHAR(64) NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, item_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_sent_items_hash ON sent_items(item_hash);
        CREATE INDEX IF NOT EXISTS idx_sent_items_sent_at ON sent_items(sent_at);
        """
        try:
            cursor.execute(create_table_query)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(self.TABLE_CREATE_ERR % 'sent_items') from e
        else:
            self.logger.info(self.TABLE_CREATE_MSG % 'sent_items')

    def insert_users(self, users: list[User], update=False) -> None:
        """Inserts/Updates user objects into database.
        If `update=False`, insert only.
        """
        conn, cursor = self._ensure_connected()

        # Though may have been validated before calling, validate again
        validated_users: list[User] = []
        for user in users:
            try:
                validated_user = validate_user(user)
                validated_users.append(validated_user)
            except ValueError as e:
                self.logger.warning(f"Skipping invalid user: {e}")
                continue
        if not validated_users:
            self.logger.warning("No valid users to insert/update.")
            return

        if not update:
            query = sql.SQL(
                "INSERT INTO users ({cols}) VALUES ({vals});"
            ).format(
                cols=sql.SQL(', ').join(map(sql.Identifier, ALLOWED_COLS)),
                vals=sql.SQL(', ').join(map(sql.Placeholder, ALLOWED_COLS)),
            )
        else:
            conflict_col = 'username'
            query = sql.SQL(
                """
                INSERT INTO users ({cols}) VALUES ({vals})
                ON CONFLICT ({conflict}) DO UPDATE SET {updates};
                """
            ).format(
                cols=sql.SQL(', ').join(map(sql.Identifier, ALLOWED_COLS)),
                vals=sql.SQL(', ').join(map(sql.Placeholder, ALLOWED_COLS)),
                conflict=sql.Identifier(conflict_col),
                updates=sql.SQL(', ').join(
                    sql.SQL("{col} = EXCLUDED.{col}").format(
                        col=sql.Identifier(field)
                    )
                    for field in ALLOWED_COLS
                    if field != conflict_col
                ),
            )
        self.logger.debug(query.as_string(conn))

        values = [
            {field: getattr(user, field) for field in ALLOWED_COLS}
            for user in validated_users
        ]

        try:
            cursor.executemany(query, values)
            conn.commit()
        except psycopg2.errors.UniqueViolation as e:
            conn.rollback()
            raise RuntimeError("User already exists.") from e
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                f"Unable to insert{'/update' if update else ''} users."
            ) from e
        else:
            self.logger.info(
                f"Inserted{'/Updated' if update else ''} "
                f"{cursor.rowcount} users."
            )

    def update_user(
        self, username: str, updates: dict[str, str | int | list[str]]
    ) -> None:
        """Validates and updates user fields from a dict."""
        conn, cursor = self._ensure_connected()

        # Validate all keys are in the whitelist
        invalid_keys: set[str] = set(updates.keys()) - set(ALLOWED_COLS)
        if invalid_keys:
            raise ValueError(
                f"Unable to update user: {username}\n"
                f"Invalid fields: {invalid_keys}"
            )
        # Validate values
        for k, v in updates:
            validate_user_field(username, k, v)

        set_clause = sql.SQL(', ').join(
            sql.SQL("{col} = {val}").format(
                col=sql.Identifier(k), val=sql.Placeholder(k)
            )
            for k in updates.keys()
        )
        query = sql.SQL(
            "UPDATE users SET {updates} WHERE username = %(username)s;"
        ).format(updates=set_clause)
        self.logger.debug(query.as_string(conn))

        values = updates | {'username': username}

        try:
            cursor.execute(query, values)
            if cursor.rowcount == 0:
                raise ValueError("User not found.")
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Unable to update user: {username}") from e
        else:
            self.logger.info(f"Updated user: {username}")

    def delete_user(self, username: str) -> None:
        """Deletes a specific user by username."""
        conn, cursor = self._ensure_connected()

        query = "DELETE FROM users WHERE username = %s;"
        try:
            cursor.execute(query, (username,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Unable to delete user: {username}") from e
        else:
            self.logger.info(f"Deleted user: {username}")

    def get_all_users(self) -> list[User]:
        """Retrieves all users from database."""
        conn, cursor = self._ensure_connected()

        query = sql.SQL(
            "SELECT {cols} FROM users ORDER BY id;".format(
                cols=sql.SQL(', ').join(map(sql.Identifier, fields(User)))
            )
        )
        self.logger.debug(query.as_string(conn))

        try:
            cursor.execute(query)
        except Exception as e:
            raise RuntimeError("Unable to fetch users.") from e
        else:
            return [User(*row) for row in cursor.fetchall()]

    def get_user_by_username(self, username: str) -> User | None:
        """Retrieves a specific user by username."""
        conn, cursor = self._ensure_connected()

        query = sql.SQL(
            "SELECT {cols} FROM users WHERE username = %s;".format(
                cols=sql.SQL(', ').join(map(sql.Identifier, fields(User)))
            )
        )
        self.logger.debug(query.as_string(conn))

        try:
            cursor.execute(query, (username,))
        except Exception as e:
            raise RuntimeError(f"Unable to fetch user: {username}") from e
        else:
            row = cursor.fetchone()
            if row:
                return User(*row)
            return None

    def get_sent_item_hashes(
        self, user_id: int, item_hashes: list[str]
    ) -> set[str]:
        """Returns which item hashes have already been sent to this user."""
        if not item_hashes:
            return set()

        conn, cursor = self._ensure_connected()

        query = """
        SELECT item_hash FROM sent_items
        WHERE user_id = %s AND item_hash = ANY(%s);
        """
        try:
            cursor.execute(query, (user_id, item_hashes))
        except Exception as e:
            raise RuntimeError("Unable to check hashes.") from e
        else:
            return {row[0] for row in cursor.fetchall()}

    @staticmethod
    def should_send_to_user(user: User, current_time: datetime) -> bool:
        """Checks if enough time has passed based on user's period."""
        # Never sent before, should send
        if user.last_sent_at is None:
            return True
        time_diff = current_time - user.last_sent_at
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

        conn, cursor = self._ensure_connected()

        if sent_at is None:
            sent_at = datetime.now()

        insert_query = """
        INSERT INTO sent_items (user_id, item_hash, sent_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, item_hash) DO NOTHING;
        """
        values = [(user.id, item_hash, sent_at) for item_hash in item_hashes]
        try:
            cursor.executemany(insert_query, values)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                f"Unable to insert sent hashes for: {user.username}"
            ) from e
        else:
            self.logger.info(f"Recorded {cursor.rowcount} items")

    def update_last_sent_at(
        self, user: User, sent_at: datetime | None = None
    ) -> None:
        """Updates the user's last_sent_at field."""
        conn, cursor = self._ensure_connected()

        if sent_at is None:
            sent_at = datetime.now()

        try:
            update_query = "UPDATE users SET last_sent_at = %s WHERE id = %s;"
            cursor.execute(update_query, (sent_at, user.id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                f"Unable to update last_sent_at for: {user.username}"
            ) from e
        else:
            self.logger.info(f"Updated last_sent_at for: {user.username}")

    def count_all_sent_items(self) -> int:
        """Get the number of all sent_items records."""
        conn, cursor = self._ensure_connected()

        query = "SELECT COUNT(*) FROM sent_items;"
        try:
            cursor.execute(query)
        except Exception as e:
            raise RuntimeError(
                "Unable to get the number of records in sent_items."
            ) from e
        else:
            row = cursor.fetchone()
            if row is not None:
                return row[0]
            return 0

    def cleanup_old_sent_items(self, cutoff_date: datetime) -> None:
        """Deletes sent_items records older than the cutoff date."""
        conn, cursor = self._ensure_connected()

        query = "DELETE FROM sent_items WHERE sent_at < %s;"
        try:
            cursor.execute(query, (cutoff_date,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(
                "Unable to clean up old records in sent_items."
            ) from e
        else:
            self.logger.info(
                f"Cleaned up {cursor.rowcount} old records in sent_items."
            )

    def reset_id_seq(self) -> None:
        """Reset sequence 'users_id_seq' to continue from max user id."""
        conn, cursor = self._ensure_connected()

        seq_name_query = "SELECT pg_get_serial_sequence('users', 'id');"
        reset_query = (
            "SELECT setval({}, COALESCE((SELECT MAX(id) FROM users), 0) + 1, "
            "false;"
        )
        value_query = "SELECT last_value, is_called FROM {};"
        try:
            # Get the sequence name
            cursor.execute(seq_name_query)
            row = cursor.fetchone()
            if row is None or not row[0]:
                raise ValueError("No sequence found for users.id")
            seq_name = row[0]
            # Get current value
            cursor.execute(sql.SQL(value_query).format(sql.Literal(seq_name)))
            last_value_old, is_called = cursor.fetchone()
            # Reset to the max user id + 1 (is_called = false)
            cursor.execute(sql.SQL(reset_query).format(sql.Literal(seq_name)))
            # Check the current value
            cursor.execute(sql.SQL(value_query).format(sql.Literal(seq_name)))
            last_value_new, is_called = cursor.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError("Unable to reset 'users_id_seq'.") from e
        else:
            self.logger.info(
                f"Reset '{seq_name}': {last_value_old} -> {last_value_new} "
                f"(is_called: {is_called})"
            )

    def truncate_tables(
        self, table_name: str, cascade=False, restart_identity=True
    ) -> None:
        """Truncate (remove all rows from) a table."""
        conn, cursor = self._ensure_connected()

        try:
            cursor.execute(self.CHECK_TABLE_QUERY, (table_name,))
        except Exception as e:
            raise RuntimeError(self.TABLE_CHECK_ERR % table_name) from e

        row = cursor.fetchone()
        if row is None or not row[0]:
            self.logger.info(f"Table not found: {table_name}. Skipping...")
            return

        truncate_query = sql.SQL("TRUNCATE TABLE {} {} {};").format(
            sql.Identifier(table_name),
            sql.SQL(
                "RESTART IDENTITY" if restart_identity else "CONTINUE IDENTITY"
            ),
            sql.SQL("CASCADE" if cascade else ""),
        )
        try:
            cursor.execute(truncate_query)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError("Unable to reset users_id_seq.") from e
        else:
            self.logger.info(
                f"Truncated table: {table_name}"
                f"(cascade: {cascade}, restart_identity: {restart_identity})"
            )


def initialize_db(logger: Logger | MyLogger = getLogger()) -> UserServiceDB:
    """Initialize and connect to the database."""
    try:
        pg_password = Path('./.pg_password').read_text().strip()
    except Exception:
        pg_password = getpass("Enter your PostgreSQL password: ")
    db = UserServiceDB(password=pg_password, logger=logger)
    return db
