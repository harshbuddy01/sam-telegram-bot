"""
Telegram Premium & Aesthetic UI Helper
Provides custom emoji tags, unicode styling, banners, and layout dividers.
"""

from typing import Optional

def format_emoji(fallback: str, custom_id: Optional[str] = None) -> str:
    """
    Formats an emoji for HTML parse_mode.
    If custom_id is provided, wraps in <tg-emoji emoji-id="...">fallback</tg-emoji>.
    """
    if custom_id and str(custom_id).strip():
        return f'<tg-emoji emoji-id="{custom_id.strip()}">{fallback}</tg-emoji>'
    return fallback

class UI:
    # Decorative Borders & Headers
    HEADER_START = "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮"
    HEADER_END   = "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
    DIVIDER      = "───────────────────────────────"
    SECTION_BAR  = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Bullet points & Badges
    BULLET = "✦"
    STAR = "★"
    DIAMOND = "◈"
    CHECK = "✔"
    ARROW = "➜"
    DOT = "•"

class Emojis:
    # Navigation & Actions
    SHOP = "🛍️"
    WALLET = "💳"
    PROFILE = "👤"
    SUPPORT = "🛟"
    REFER = "🎁"
    ADMIN = "⚡"
    BACK = "◀️"
    HOME = "🏠"
    CANCEL = "❌"
    CHECK = "✅"
    FIRE = "🔥"
    STAR = "⭐"
    SPARKLES = "✨"
    DIAMOND = "💎"
    CROWN = "👑"
    
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
    
    # Category Icons
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
