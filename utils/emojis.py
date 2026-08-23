"""
Telegram Premium & Aesthetic UI Helper
Provides custom emoji tags, luxury formatting, borders, and typography.
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
    # Modern Minimalist Dividers & Headers
    BORDER_TOP = "╭─────────────────────────────╮"
    BORDER_BOT = "╰─────────────────────────────╯"
    LINE       = "───────────────────────────────"
    BAR        = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    SECTION_BAR = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Bullet points & Badges
    BULLET = "✦"
    STAR   = "★"
    DIAMOND= "◈"
    CHECK  = "✔"
    ARROW  = "➜"
    DOT    = "•"
    FIRE   = "🔥"
    CROWN  = "👑"

class Emojis:
    # Navigation & Actions
    SHOP = "🛍️"
    SEARCH = "🔍"
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
    GUIDE = "📖"
    ORDERS = "📦"
    
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
    STREAMING = "🍿"
    VPN = "🛡️"
    EDUCATION = "🎓"
    AI_TOOLS = "🤖"
    GAMING = "🎮"
    MUSIC = "🎵"
    UTILITIES = "🛠️"
    DESIGN = "🎨"
    TELEGRAM = "✈️"

    # User & Stats
    ID = "🆔"
    CALENDAR = "📅"
    STATS = "📊"
    NOTIFICATION = "🔔"
    WITHDRAW = "📤"
    API = "⚙️"
    LINK = "🔗"
    DOT = "•"
    BULLET = "✦"
