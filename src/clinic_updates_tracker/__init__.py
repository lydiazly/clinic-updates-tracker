# src/clinic_updates_tracker/__init__.py
from dotenv import load_dotenv
import os
from pathlib import Path


load_dotenv()

OUTPUT_HTML_NAME = os.getenv('OUTPUT_HTML_NAME', 'content.html')

# OUTPUT_HTML_PATH: str = os.getenv('OUTPUT_HTML_PATH', f'./output/{OUTPUT_HTML_NAME}')
OUTPUT_HTML_PATH: Path = Path(os.getenv('OUTPUT_HTML_PATH', f'./output/{OUTPUT_HTML_NAME}'))

if OUTPUT_HTML_PATH.is_dir():
    OUTPUT_HTML_PATH = OUTPUT_HTML_PATH / OUTPUT_HTML_NAME

TARGET_BASE_URL: str = os.getenv('TARGET_BASE_URL', '')

TARGET_TZ: str = os.getenv('TARGET_TZ', '')

CITY: str = os.getenv('CITY', 'Unknown')

DAYS_SINCE: int = int(os.getenv('DAYS_SINCE', 30))  # default: 1 month

MAX_N_ITEMS: int = int(os.getenv('MAX_N_ITEMS'), 10)  # default: 10 items

BROWSER_CHOICES = ["chromium", "firefox", "webkit"]

# INPUT_USERS_JSON_PATH: str = os.getenv('INPUT_USERS_JSON_PATH', './input/users.json')
INPUT_USERS_JSON_PATH: Path = Path(os.getenv('INPUT_USERS_JSON_PATH', './input/users.json'))
