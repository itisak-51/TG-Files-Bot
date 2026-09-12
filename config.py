"""
Central configuration. Everything sensitive lives in .env — never in code.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID_RAW = os.getenv("OWNER_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "filestore.db").strip()
LOG_PATH = os.getenv("LOG_PATH", "bot.log").strip()

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    sys.exit(
        "\n[CONFIG ERROR] BOT_TOKEN is missing or invalid.\n"
        "1. Copy .env.example to .env\n"
        "2. Get a token from @BotFather on Telegram\n"
        "3. Paste it as BOT_TOKEN=... in .env\n"
    )

if not OWNER_ID_RAW.isdigit():
    sys.exit(
        "\n[CONFIG ERROR] OWNER_ID is missing or invalid.\n"
        "1. Message @userinfobot on Telegram to get your numeric user ID\n"
        "2. Set OWNER_ID=<your id> in .env\n"
    )

OWNER_ID = int(OWNER_ID_RAW)

# Default settings written into the DB on first run (editable live via /admin after that)
DEFAULT_AUTO_DELETE_SECONDS = 300  # 5 minutes
DEFAULT_PROTECT_CONTENT = "0"  # "1" = forwarding/saving disabled on delivered files

# Optional. If set, every uploaded file is also mirrored to DevUploads.com.
# Not required to run the bot — leave blank to skip DevUploads entirely.
# Once the bot is running, this can be viewed/changed live from
# Admin Panel -> Settings -> DevUploads without touching .env or restarting.
DEVUPLOADS_API_KEY = os.getenv("DEVUPLOADS_API_KEY", "").strip()
