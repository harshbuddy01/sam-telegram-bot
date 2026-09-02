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
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@SAM_HUB_OP")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/SamStoreServices")
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/+qNcj-Lx4pQZmMjE1")
NOTIFICATION_CHANNEL_ID = int(os.getenv("NOTIFICATION_CHANNEL_ID", "-1004403882109"))
REFERRAL_BONUS_PERCENT = float(os.getenv("REFERRAL_BONUS_PERCENT", "5.0"))

# Automated Payment Gateways (Razorpay & PayPal)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "SamStoreSecret2026")

# PayPal Settings
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip('"\' ')
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip('"\' ')
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "LIVE").strip('"\' ').upper()
PAYPAL_CURRENCY = os.getenv("PAYPAL_CURRENCY", "USD").strip('"\' ').upper()
PAYPAL_USD_TO_INR_RATE = float(os.getenv("PAYPAL_USD_TO_INR_RATE", "90.0"))
PAYPAL_SURCHARGE_PERCENT = float(os.getenv("PAYPAL_SURCHARGE_PERCENT", "0.0"))
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "").strip('"\' ')

# OxaPay Crypto Settings
OXAPAY_MERCHANT_KEY = os.getenv("OXAPAY_MERCHANT_KEY", "").strip('"\' ')
OXAPAY_CURRENCY = os.getenv("OXAPAY_CURRENCY", "USDT").strip('"\' ').upper()
OXAPAY_USD_TO_INR_RATE = float(os.getenv("OXAPAY_USD_TO_INR_RATE", "90.0"))
OXAPAY_SURCHARGE_PERCENT = float(os.getenv("OXAPAY_SURCHARGE_PERCENT", "0.0"))
OXAPAY_CALLBACK_URL = os.getenv("OXAPAY_CALLBACK_URL", "https://sam-telegram-bot-production-11f2.up.railway.app/webhook/oxapay").strip('"\' ')

# Database
DB_PATH = os.getenv("DB_PATH", "store.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
