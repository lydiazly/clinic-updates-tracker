# src/clinic_updates_tracker/__init__.py
from dotenv import load_dotenv
import os
# from pathlib import Path

load_dotenv()

# local_directory: str = os.environ.get(
#     "XDG_DATA_HOME", os.path.join(Path.home(), ".local/share")
# )
# os.makedirs(local_directory, exist_ok=True)

# LAST_RUN_AT_FILE_NAME: str = os.path.join(local_directory, "clinic_updates_lastrun.txt")
# LAST_RUN_AT_ABSOLUTE_PATH: str = os.path.abspath(
#     os.path.join(Path.home(), LAST_RUN_AT_FILE_NAME)
# )

HTML_FILE_NAME: str = "./tmp_content.html"

TARGET_BASE_URL: str = os.getenv('TARGET_BASE_URL') or ''

CITY: str = os.getenv('CITY') or 'Unknown'

DAYS_SINCE: int = int(os.getenv('DAYS_SINCE')) or 30  # default: 1 month

MAX_N_ITEMS: int = int(os.getenv('MAX_N_ITEMS')) or 10  # default: 10 items

BROWSER_CHOICES = ["chromium", "firefox", "webkit"]
