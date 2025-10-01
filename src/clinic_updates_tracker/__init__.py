# src/clinic_updates_tracker/__init__.py
from dotenv import load_dotenv
import os


load_dotenv()

OUTPUT_DIR = "./output"

os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_NAME: str = os.path.join(OUTPUT_DIR, "content.html")

TARGET_BASE_URL: str = os.getenv('TARGET_BASE_URL') or ''

TARGET_TZ: str = os.getenv('TARGET_TZ') or ''

CITY: str = os.getenv('CITY') or 'Unknown'

DAYS_SINCE: int = int(os.getenv('DAYS_SINCE')) or 30  # default: 1 month

MAX_N_ITEMS: int = int(os.getenv('MAX_N_ITEMS')) or 10  # default: 10 items

BROWSER_CHOICES = ["chromium", "firefox", "webkit"]
