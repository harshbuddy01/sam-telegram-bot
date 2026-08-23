"""
Telegram Premium & Aesthetic UI Helper
Provides custom emoji tags, luxury formatting, borders, and typography.
"""

from typing import Optional

class CustomEmojis:
    # Luxury UI Accents
    CROWN = "5447410659077661506"
    STAR = "5409048419211682843"
    FIRE = "5251203410396458957"
    DIAMOND = "5282843764451195532"
    SPARKLE = "5458603043203327669"
    VERIFIED = "5260293700088511294"
    CHECK = "6296501388276926215"
    KEY = "5879982576671657703"
    WARRANTY = "6298670698948724690"
    LOCK = "6219532735359223977"

    # Navigation & Core Hubs
    SHOP = "5879753496000991296"
    SEARCH = "5877697061364698656"
    WALLET = "5872815276982014467"
    ORDERS = "5877576553172308576"
    REFER = "5913528148154126357"
    SUPPORT = "5877739680325179188"
    CARD = "6296367896398399651"

    # Products & Services
    NETFLIX = "5877576553172308576"
    PRIME = "5807506103063286427"
    YOUTUBE = "5807418060528685532"
    SPOTIFY = "5868508172108435919"
    APPLE_MUSIC = "5872815276982014467"
    CRUNCHYROLL = "5796283422238314412"
    CHATGPT = "5364075889669718872"
    CLAUDE = "6257949774712932243"
    CANVA = "5274114750228210079"
    CAPCUT = "4985619816975958694"
    NORDVPN = "4958909307987952352"
    TELEGRAM = "6260133413395631094"
    DISCORD = "6260370336676580815"
    ZEE5 = "6262548271642709405"
    HOTSTAR = "6262294207147281305"

def format_emoji(fallback: str, custom_id: Optional[str] = None) -> str:
    """
    Formats an emoji for HTML parse_mode.
    If custom_id is provided, wraps in <tg-emoji emoji-id="...">fallback</tg-emoji>.
    """
    if custom_id and str(custom_id).strip():
        return f'<tg-emoji emoji-id="{custom_id.strip()}">{fallback}</tg-emoji>'
    return fallback

def ce(custom_id: str, fallback: str = "✨") -> str:
    """Shortcut for custom emoji rendering"""
    return format_emoji(fallback, custom_id)

class UI:
    BORDER_TOP = "╭─────────────────────────────╮"
    BORDER_BOT = "╰─────────────────────────────╯"
    LINE       = "───────────────────────────────"
    BAR        = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    SECTION_BAR = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    BULLET = "✦"
    STAR   = "★"
    DIAMOND= "◈"
    CHECK  = "✔"
    ARROW  = "➜"
    DOT    = "•"
    FIRE   = "🔥"
    CROWN  = "👑"

class Emojis:
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
    
    STREAMING = "🍿"
    VPN = "🛡️"
    EDUCATION = "🎓"
    AI_TOOLS = "🤖"
    GAMING = "🎮"
    MUSIC = "🎵"
    UTILITIES = "🛠️"
    DESIGN = "🎨"
    TELEGRAM = "✈️"

    ID = "🆔"
    CALENDAR = "📅"
    STATS = "📊"
    NOTIFICATION = "🔔"
    WITHDRAW = "📤"
    API = "⚙️"
    LINK = "🔗"
    DOT = "•"
    BULLET = "✦"
