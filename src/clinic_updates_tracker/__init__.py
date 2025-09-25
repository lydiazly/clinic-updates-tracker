# src/clinic_updates_tracker/__init__.py
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()

local_directory: str = os.environ.get(
    "XDG_DATA_HOME", os.path.join(Path.home(), ".local/share")
)
os.makedirs(local_directory, exist_ok=True)

last_run_at_file_name: str = os.path.join(local_directory, "clinic_updates_lastrun.txt")
last_run_at_absolute_path: str = os.path.abspath(
    os.path.join(Path.home(), last_run_at_file_name)
)

target_base_url: str = os.getenv('TARGET_BASE_URL')
default_city: str = os.getenv('DEFAULT_CITY')


browser_choices = ["chromium", "firefox", "webkit"]
