import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()] if admin_ids_str else []

STORAGE_FILE = "database/chats_storage.json"
directory = os.path.dirname(STORAGE_FILE)
if directory and not os.path.exists(directory):
    os.makedirs(directory)

LANGUAGES_FILE = "database/user_languages.json"
directory = os.path.dirname(STORAGE_FILE)
if directory and not os.path.exists(directory):
    os.makedirs(directory)


LAST_MESSAGES_COUNT = 6
PAGE_CHAR_LIMIT = 512
