import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Parse Admin IDs list
admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()]

# Store & Branding Config
STORE_NAME = os.getenv("STORE_NAME", "SamStore Services")
BANNER_IMAGE_URL = os.getenv("BANNER_IMAGE_URL", "")

# UPI & Payment Settings
UPI_ID = os.getenv("UPI_ID", "your-upi@okhdfcbank")
UPI_NAME = os.getenv("UPI_NAME", "Sam Store Services")
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "₹")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@OTT_Support")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/SamStoreServices")
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/SamStoreServices")
NOTIFICATION_CHANNEL_ID = int(os.getenv("NOTIFICATION_CHANNEL_ID", "0"))
REFERRAL_BONUS_PERCENT = float(os.getenv("REFERRAL_BONUS_PERCENT", "5.0"))

# Automated Payment Gateways (Razorpay & Cashfree)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID", "")
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY", "")
CASHFREE_ENV = os.getenv("CASHFREE_ENV", "PRODUCTION")

# Database
DB_PATH = os.getenv("DB_PATH", "store.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
