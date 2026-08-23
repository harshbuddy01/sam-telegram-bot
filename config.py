import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Parse Admin IDs list
admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()]

# Store & UPI Config
UPI_ID = os.getenv("UPI_ID", "your-upi@okhdfcbank")
UPI_NAME = os.getenv("UPI_NAME", "OTT Store")
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "₹")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@OTT_Support")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/your_channel")
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/your_group")
REFERRAL_BONUS_PERCENT = float(os.getenv("REFERRAL_BONUS_PERCENT", "5.0"))

# Database
DB_PATH = os.getenv("DB_PATH", "store.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
