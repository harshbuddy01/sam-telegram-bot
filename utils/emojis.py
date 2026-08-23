"""
Telegram Emoji & Premium Custom Emoji Helper.
Supports both standard high-quality Unicode emojis and custom Telegram Premium Emoji IDs.
"""

from typing import Optional

def format_emoji(fallback: str, custom_id: Optional[str] = None) -> str:
    """
    Formats an emoji for HTML parse_mode.
    If custom_id is provided, wraps in <tg-emoji emoji-id="...">fallback</tg-emoji>.
    Otherwise returns fallback Unicode emoji.
    """
    if custom_id and str(custom_id).strip():
        return f'<tg-emoji emoji-id="{custom_id.strip()}">{fallback}</tg-emoji>'
    return fallback

class Emojis:
    # Navigation & Actions
    SHOP = "🛍️"
    WALLET = "💳"
    PROFILE = "👤"
    SUPPORT = "🛟"
    REFER = "🎁"
    ADMIN = "⚙️"
    BACK = "🔙"
    CANCEL = "❌"
    CHECK = "✅"
    FIRE = "🔥"
    STAR = "⭐"
    SPARKLES = "✨"
    DIAMOND = "💎"
    
    # Store & Products
    CATEGORY = "📁"
    PRODUCT = "📦"
    TAG = "🏷️"
    PRICE = "💰"
    STOCK = "📊"
    LIGHTNING = "⚡"
    LOCK = "🔒"
    KEY = "🔑"
    INFO = "ℹ️"
    DOCUMENT = "📝"
    WARRANTY = "🛡️"
    ROCKET = "🚀"
    CART = "🛒"
    
    # Categories Default Badges
    STREAMING = "🎬"
    VPN = "🛡️"
    EDUCATION = "🎓"
    AI_TOOLS = "🤖"
    GAMING = "🎮"
    MUSIC = "🎵"
    UTILITIES = "🛠️"
    PAID_SERVICES = "💼"
    FREEBIES = "🎁"

    # User & Stats
    ID = "🆔"
    CALENDAR = "📅"
    STATS = "📊"
    NOTIFICATION = "🔔"
    ORDERS = "📜"
    WITHDRAW = "📤"
    API = "⚙️"
    LINK = "🔗"
    ARROW_RIGHT = "➡️"
    ARROW_DOWN = "⬇️"
    DOT = "•"
    BULLET = "✦"
