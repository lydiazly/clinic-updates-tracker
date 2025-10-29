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
from psycopg2.extras import execute_values
from textwrap import dedent
from typing import TypedDict

from clinictracker.user.models import User, ALLOWED_COLS
from clinictracker.user.config import PG_PASSWORD_PATH
from clinictracker.startup import MyLogger
from clinictracker.user.helpers import get_valid_user, validate_user_field


class ConnParams(TypedDict):
    host: str
    port: int
    database: str
    user: str
    password: str


class UserServiceDB:
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

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5432,
        database: str = 'userservice',
        user: str = 'admin',
        password: str | None = None,
        pg_password_path: Path = PG_PASSWORD_PATH,
        dryrun: bool = False,
        logger: Logger | MyLogger = getLogger(),
    ) -> None:
        self.conn: psycopg2.extensions.connection | None = None
        self.cur: psycopg2.extensions.cursor | None = None
        self.dryrun: bool = dryrun
        self.logger: Logger | MyLogger = logger
        # Initialize
        if password is None:
            logger.debug(
                f"Loading password from {PG_PASSWORD_PATH}... "
                "(set $PG_PASSWORD_PATH to load from another file)"
            )
            try:
                password = pg_password_path.read_text().strip()
            except Exception as e:
                logger.debug(f"Unable to load password: {e}")
                password = getpass("Enter your PostgreSQL password: ").strip()
                logger.debug(f"Got password with {len(password)} characters.")
            else:
                logger.debug("Password loaded.")

        self.conn_params: ConnParams = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password,
        }

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
        if self.conn is None or self.cur is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self.conn, self.cur

    def connect(self) -> None:
        """Establishes database connection."""
        try:
            self.conn = psycopg2.connect(**self.conn_params)
            self.cur = self.conn.cursor()
        except Exception as e:
            raise RuntimeError("Error connecting to database.") from e
        else:
            self.logger.info(self.CONNECT_MSG)

    def close(self) -> None:
        """Closes database connection."""
        errors = []

        if self.cur is not None:
            try:
                self.cur.close()
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

    def create_users_table(self) -> bool:
        """Creates 'users' table. Returns `True` if created.
        - Columns: id, username, nickname, emails, cities, period, nmax,
                   last_sent_at, created_at, updated_at
        - Primary key: id
        """
        conn, cur = self._ensure_connected()

        try:
            cur.execute(self.CHECK_TABLE_QUERY, ('users',))
        except Exception as e:
            raise RuntimeError(self.TABLE_CHECK_ERR % 'users') from e

        row = cur.fetchone()
        if row and row[0]:
            self.logger.info(self.TABLE_EXIST_MSG % 'users')
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
                last_sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
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
            raise RuntimeError(self.TABLE_CREATE_ERR % 'users') from e
        else:
            self.logger.info(self.TABLE_CREATE_MSG % 'users')
            return not self.dryrun

    def create_sent_items_table(self) -> bool:
        """Creates 'sent_items' table for tracking sent items per user.
        Returns `True` if created.
        - Columns: user_id, item_hash, sent_at
        - Primary key: (user_id, item_hash)
        - Foreign key: user_id references users(id)
        """
        conn, cur = self._ensure_connected()

        try:
            cur.execute(self.CHECK_TABLE_QUERY, ('sent_items',))
        except Exception as e:
            raise RuntimeError(self.TABLE_CHECK_ERR % 'sent_items') from e

        row = cur.fetchone()
        if row and row[0]:
            self.logger.info(self.TABLE_EXIST_MSG % 'sent_items')
            return True

        query = dedent(
            """
            CREATE TABLE IF NOT EXISTS sent_items (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                item_hash VARCHAR(64) NOT NULL,
                sent_at TIMESTAMP DEFAULT now(),
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
            raise RuntimeError(self.TABLE_CREATE_ERR % 'sent_items') from e
        else:
            self.logger.info(self.TABLE_CREATE_MSG % 'sent_items')
            return not self.dryrun

    def insert_users(self, users: list[User], update=False) -> None:
        """Inserts/Updates `User` objects into database and increment
        sequence only after inserting new rows.
        If `update=False`, insert only.
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
            return

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
        ).format(
            tb=tmp_tb_sql,
            updates=set_sql,
        )
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
        ).format(
            tb=tmp_tb_sql,
            cols=cols_sql,
            tmp_cols=tmp_cols_sql,
        )
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
        #     return
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
                for user in validated_users:
                    if user.username not in inserted_usernames:
                        self.logger.warning(
                            self.USER_EXIST_MSG % user.username
                        )
            if insert_count > 0:
                self.logger.info(
                    f"Inserted {insert_count} users: "
                    + ', '.join(inserted_usernames)
                )

    def update_user(
        self, username: str, updates: dict[str, str | int | list[str]]
    ) -> None:
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

    @staticmethod
    def should_send_to_user(user: User, current_time: datetime) -> bool:
        """Checks if enough time has passed based on user's period.
        Automatically handles timezone conversion for timezone-aware objects.
        """
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
            self.logger.info(f"Recorded {cur.rowcount} items")

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

    def get_row_count(self, tb: str) -> int:
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
                return row[0]
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

        # seq_query = "SELECT pg_get_serial_sequence('users', 'id');"
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
            # Get the sequence name
            # cur.execute(seq_query)
            # row = cur.fetchone()
            # if row is None or row[0] is None:
            #     raise ValueError("No sequence for users.id")
            # seq_name = row[0].split('.')[-1]  # remove 'public.'
            # self.logger.debug(f"Sequence name: {seq_name}")
            # Get current value
            # cur.execute(sql.SQL(value_query).format(sql.Identifier(seq_name)))
            cur.execute(value_query)
            last_value_old, is_called = cur.fetchone()
            # Reset to the max user id + 1 (is_called = false)
            # cur.execute(sql.SQL(reset_query).format(sql.Literal(seq_name)))
            cur.execute(reset_query)
            # Check the current value
            # cur.execute(sql.SQL(value_query).format(sql.Identifier(seq_name)))
            cur.execute(value_query)
            last_value_new, is_called = cur.fetchone()
            if not self.dryrun:
                conn.commit()
            else:
                conn.rollback()
        except Exception as e:
            conn.rollback()
            raise RuntimeError("Unable to reset 'users_id_seq'.") from e
        else:
            next_seq = last_value_new + 1 if is_called else last_value_new
            self.logger.debug(
                f"users_id_seq: {last_value_old} -> {last_value_new} "
                f"(is_called: {is_called})"
            )
            self.logger.info(f"Reset. Next user id: {next_seq}")

    def truncate_table(
        self, table_name: str, cascade=False, restart_identity=True
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
#     logger: Logger | MyLogger = getLogger(),
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
#         logger.debug(f"Loaded password from: {str(pg_password_path)}")
#     db = UserServiceDB(password=pg_password, dryrun=dryrun, logger=logger)
#     return db
