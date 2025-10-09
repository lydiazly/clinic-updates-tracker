# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/db_manager.py

from dataclasses import dataclass, field, asdict
from getpass import getpass
import json
import re
from pathlib import Path
import psycopg2

from clinic_updates_tracker import DAYS_SINCE, MAX_N_ITEMS, INPUT_USERS_JSON_PATH


@dataclass
class User:
    username: str
    nickname: str | None = None
    email_list: list[str] = field(default_factory=list)
    city_list: list[str] = field(default_factory=list)
    intv: int = DAYS_SINCE
    nmax: int = MAX_N_ITEMS
    id: int = -1  # assigned by database

    def __str__(self):
        return """id: %(id)d
username: %(username)s
nickname: %(nickname)s
email_list: %(email_list)s
city_list: %(city_list)s
intv: %(intv)d
nmax: %(nmax)d""" % asdict(self)


class UserServiceDB:
    # Reasonable email regex for basic validation
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?'
        r'(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)+$'
    )

    def __init__(
        self,
        host='localhost',
        port=5432,
        database='userservice',
        user='admin',
        password='admin',
    ):
        self.conn_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password,
        }
        self.conn = None
        self.cursor = None


    def connect(self):
        """Establishes database connection."""
        self.conn = psycopg2.connect(**self.conn_params)
        self.cursor = self.conn.cursor()
        print("Connected to PostgreSQL database.")


    def close(self):
        """Closes database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("Database connection closed.")


    def create_table(self):
        """Creates the 'users' table with schema.
        - username: (str, unique, not null) the primary email
        - nickname: (str), default to null
        - email_list: (list(str), not empty) recipients (may include the primary email)
        - city_list: (list(str), not empty) city/town list
        - intv: (int, > 0) schedule interval in days, default to 1
        - nmax: (int, > 0) max number of items to show, default to 10
        """
        # Check if table exists
        check_table_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'users'
        );
        """
        self.cursor.execute(check_table_query)
        table_exists = self.cursor.fetchone()[0]

        if table_exists:
            print("Table 'users' already exists. Skipping creation.\n")
            return

        # Create table
        # Only a simple check for username, other validation is done by is_valid_email()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL CHECK (username LIKE '%@%.%'),
            nickname VARCHAR(30),
            email_list VARCHAR(255)[] NOT NULL CHECK (array_length(email_list, 1) >= 1),
            city_list VARCHAR(100)[] NOT NULL CHECK (array_length(city_list, 1) >= 1),
            intv INTEGER DEFAULT 1 CHECK (intv > 0),
            nmax INTEGER DEFAULT 10 CHECK (nmax > 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        self.cursor.execute(create_table_query)
        self.conn.commit()
        print("Table 'users' created successfully.\n")


    @classmethod
    def is_valid_email(cls, email: str) -> bool:
        """Checks if email format is valid."""
        return bool(cls.EMAIL_PATTERN.match(email)) if email else False


    def validate_user(self, user: User) -> User:
        """Validates user data."""
        # Validate username
        if not self.is_valid_email(user.username):
            raise ValueError(f"Invalid username email format: {user.username}")

        # Validate email_list
        if not user.email_list:
            raise ValueError(f"{user.username}: empty 'email_list'")
        for email in user.email_list:
            if not self.is_valid_email(email):
                raise ValueError(f"{user.username}: Invalid email: {email}")

        # Validate city_list
        if not user.city_list:
            raise ValueError(f"{user.username}: empty 'city_list'")
        # Validate numeric fields
        if user.intv <= 0:
            raise ValueError(f"{user.username}: 'intv' must be positive, got {user.intv}")
        if user.nmax <= 0:
            raise ValueError(f"{user.username}: 'nmax' must be positive, got {user.nmax}")

        return user


    def insert_users(self, users: list[User]):
        """Insert users into database."""
        validated_users = []
        for user in users:
            try:
                validated_user = self.validate_user(user)
                validated_users.append(validated_user)
            except ValueError as e:
                print(f"WARNING: Skipping invalid user: {e}")
                continue

        if not validated_users:
            print("WARNING: No valid users to insert.")
            return

        insert_query = """
        INSERT INTO users (username, nickname, email_list, city_list, intv, nmax)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (username) DO UPDATE SET
            nickname = EXCLUDED.nickname,
            email_list = EXCLUDED.email_list,
            city_list = EXCLUDED.city_list,
            intv = EXCLUDED.intv,
            nmax = EXCLUDED.nmax;
        """

        values = [
            (u.username, u.nickname, u.email_list, u.city_list, u.intv, u.nmax)
            for u in validated_users
        ]

        self.cursor.executemany(insert_query, values)
        self.conn.commit()
        print(f"Inserted/Updated {len(validated_users)} users")


    def get_all_users(self) -> list[User]:
        """Retrieve all users from database."""
        query = "SELECT username, nickname, email_list, city_list, intv, nmax, id FROM users ORDER BY username;"
        self.cursor.execute(query)

        users = []
        for row in self.cursor.fetchall():
            users.append(User(*row))

        return users


    def get_user_by_username(self, username: str) -> User | None:
        """Retrieve a specific user by username"""
        query = "SELECT username, nickname, email_list, city_list, intv, nmax, id FROM users WHERE username = %s;"
        self.cursor.execute(query, (username,))

        row = self.cursor.fetchone()
        if row:
            return User(*row)
        return None


def load_json_data(json_file_path: Path) -> list[User]:
        """Load and validate JSON data from file."""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"{str(json_file_path)}: file not found")
        except Exception as e:
            raise RuntimeError(f"Failed to load file '{str(json_file_path)}': {e}")

        if not isinstance(data, list):
            raise ValueError("JSON file must contain a list of user objects.")

        users = []
        for user_dict in data:
            try:
                users.append(User(**user_dict))
            except TypeError as e:
                raise TypeError(f"{user_dict}: {e}")

        return users


# TODO
def compose_email(user):
    """Compose emails."""
    pass


# def get_user_data():
def main():
    """Get user data from the database."""

    # Load data from JSON file
    print("--- Loading data from JSON ---")
    users = load_json_data(INPUT_USERS_JSON_PATH)

    # Initialize database manager
    try:
        pg_password = Path('./.pg_password').read_text()
    except Exception:
        pg_password = getpass("Enter your PostgreSQL password: ")
    db = UserServiceDB(password=pg_password)

    try:
        # Connect to database
        db.connect()

        # Create table
        db.create_table()

        # Insert data
        db.insert_users(users)

        # Retrieve all users
        print("\n--- Retrieving all users ---")
        all_users = db.get_all_users()
        print(f"Total users in database: {len(all_users)}")

        # Example: Get data for your main service function
        print("\n--- Example: Processing each user ---")
        for user in all_users:
            print(f"\n{user!s}")

            # TODO
            # compose_email(user)

        # Test: Get specific user
        print("\n--- Example: Get specific user ---")
        specific_user = db.get_user_by_username('email1-1@example.com')
        if specific_user:
            print(f"Found user:\n{specific_user}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
