import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Bot Token & Admins
BOT_TOKEN = os.getenv("BOT_TOKEN", "8617134926:AAGKECEbfficK5g8ThtTfJse1SkC-h3YrR0").strip()

admin_ids_raw = os.getenv("ADMIN_IDS", "6971497666,6085016731")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()]
if not ADMIN_IDS:
    ADMIN_IDS = [6971497666, 6085016731]

# Telethon API Client Settings (Sender User Account)
API_ID_RAW = os.getenv("API_ID", "").strip()
API_ID = int(API_ID_RAW) if API_ID_RAW.isdigit() else 0
API_HASH = os.getenv("API_HASH", "").strip()
SESSION_STRING = os.getenv("SESSION_STRING", "").strip()

# Database
DB_PATH = os.getenv("DB_PATH", "promotion_bot.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Anti-Ban Broadcast Math & Calibrations (for 300-400 groups)
DEFAULT_INTERVAL_HOURS = float(os.getenv("BROADCAST_INTERVAL_HOURS", "2.0"))
MIN_DELAY_PER_GROUP = int(os.getenv("MIN_DELAY_PER_GROUP_SEC", "18"))
MAX_DELAY_PER_GROUP = int(os.getenv("MAX_DELAY_PER_GROUP_SEC", "35"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "25"))
BATCH_COOLDOWN = int(os.getenv("BATCH_COOLDOWN_SEC", "240"))  # 4 minutes cooldown per 25 groups

# Auto-Join Safe Settings
MIN_JOIN_DELAY = int(os.getenv("MIN_JOIN_DELAY_SEC", "45"))
MAX_JOIN_DELAY = int(os.getenv("MAX_JOIN_DELAY_SEC", "90"))
MAX_JOINS_PER_DAY = int(os.getenv("MAX_JOINS_PER_DAY", "40"))

# Railway Port
PORT = int(os.getenv("PORT", "8080"))

def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True  # If no admin set yet, allow the first user to access
    return user_id in ADMIN_IDS
