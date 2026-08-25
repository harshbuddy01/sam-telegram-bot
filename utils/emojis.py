"""
Telegram Premium & Aesthetic UI Helper
Provides custom emoji tags, luxury formatting, borders, and typography.
"""

import re
from typing import Optional

class CustomEmojis:
    # UI Accents
    CROWN = "5447410659077661506"
    STAR = "5409048419211682843"
    FIRE = "5251203410396458957"
    DIAMOND = "5282843764451195532"
    SPARKLE = "5458603043203327669"
    VERIFIED = "5260293700088511294"
    CHECK = "5240241223632954241"
    GIFT = "4956282853882069908"
    TROPHY = "4958529074533238201"
    HEART = "4956611513369494230"

    # Navigation
    SHOP = "4958621433509970793"
    SEARCH = "5872815276982014467"
    CROSS = "4958526153955476488"
    WALLET = "6296508771325707891"
    ORDERS = "5440670060093922400"
    REFER = "5229027828527309057"
    SUPPORT = "4913719328546751377"
    CARD = "4913871112690992374"
    DEPOSIT = "5472279086657199080"
    LOCK = "4958526153955476488"
    KEY = "5400090058030075645"
    WARRANTY = "5213179235996294999"

    # Product Brands
    NETFLIX = "5039557485157942342"
    PRIME = "5807468522099447358"
    YOUTUBE = "5807506103063286427"
    APPLE_MUSIC = "5807418060528685532"
    CRUNCHYROLL = "5807785525045629330"
    CHATGPT = "5796283422238314412"
    CLAUDE = "5364075889669718872"
    CANVA = "6257949774712932243"
    CAPCUT = "5274114750228210079"
    NORDVPN = "4985619816975958694"
    TELEGRAM = "4958909307987952352"
    DISCORD = "4958988936681620024"
    ZEE5 = "4958633635512058775"
    HOTSTAR = "6033105092851274492"
    JIO = "6034931909945985955"
    SPOTIFY = "5868508172108435919"

    # Decorative Extras
    GLOW_1 = "6035288280562404083"
    GLOW_2 = "6260133413395631094"
    GLOW_3 = "6260370336676580815"
    GLOW_4 = "6262548271642709405"
    GLOW_5 = "6262294207147281305"
    GLOW_6 = "6262356647381830975"
    GLOW_7 = "6262416459096395116"
    GLOW_8 = "5872815276982014467"
    GLOW_9 = "5877576553172308576"
    GLOW_10 = "5877697061364698656"
    GLOW_11 = "5879753496000991296"
    GLOW_12 = "5877739680325179188"
    GLOW_13 = "5913528148154126357"
    GLOW_14 = "5879982576671657703"
    GLOW_15 = "6298670698948724690"
    GLOW_16 = "6296501388276926215"
    GLOW_17 = "6219532735359223977"
    GLOW_18 = "6296367896398399651"
    GLOW_19 = "5296764741300003476"
    GLOW_20 = "5019810647165109073"
    GLOW_21 = "4994719632905470694"
    GLOW_22 = "5077907879504118499"
    GLOW_23 = "4994602212794565807"
    GLOW_24 = "6213204539135233352"
    GLOW_25 = "6192950276526181893"
    GLOW_26 = "5017122105011995219"
    GLOW_27 = "5330237710655306682"
    GLOW_28 = "5318911503938634641"
    GLOW_29 = "5346024520081751155"
    GLOW_30 = "5359437015752401733"
    GLOW_31 = "5877651964208091297"
    GLOW_32 = "5364339557712020484"

BRAND_THEMES = {
    "Netflix": "red dots",
    "Prime": "blue dots",
    "YouTube": "red+white",
    "Spotify": "green dots",
    "ChatGPT": "green+black",
    "NordVPN": "blue+dark",
    "Canva": "purple dots",
    "CapCut": "black+white",
    "Default": "gold dots"
}

def format_emoji(fallback: str = "✨", custom_id: Optional[str] = None) -> str:
    """
    Formats an emoji for HTML parse_mode.
    If custom_id is provided, wraps in <tg-emoji emoji-id="...">fallback</tg-emoji>.
    Guarantees fallback is a safe valid emoji to prevent ENTITY_TEXT_INVALID errors from Telegram.
    """
    safe_fallback = "✨"
    if fallback and isinstance(fallback, str):
        cleaned = fallback.strip()
        if cleaned and not any(0xD800 <= ord(c) <= 0xDFFF for c in cleaned):
            safe_fallback = cleaned
        else:
            safe_fallback = "✨"

    if custom_id and str(custom_id).strip().isdigit():
        return f'<tg-emoji emoji-id="{str(custom_id).strip()}">{safe_fallback}</tg-emoji>'
    return safe_fallback or "📁"

def ce(custom_id: str, fallback: str = "✨") -> str:
    """Shortcut for custom emoji rendering"""
    return format_emoji(fallback, custom_id)

def extract_clean_name_and_emoji(message) -> tuple[str, str, Optional[str]]:
    """
    Extracts:
    - clean_name: clean human-readable name without surrogate custom emoji fallbacks
    - display_emoji: clean fallback emoji (e.g. '👑' or '🍿')
    - custom_emoji_id: the 64-bit Telegram custom emoji ID string if present
    """
    if not message or not getattr(message, "text", None):
        return ("New Item", "📁", None)

    raw_text = message.text.strip()
    custom_id = None
    fallback_char = "📁"

    if getattr(message, "entities", None):
        custom_entities = [e for e in message.entities if e.type == "custom_emoji" and e.custom_emoji_id]
        if custom_entities:
            first_ent = custom_entities[0]
            custom_id = str(first_ent.custom_emoji_id)
            fallback_char = "👑"  # Safe standard fallback emoji

            # Clean text by removing surrogate pairs
            clean_text = "".join(c for c in raw_text if not (0xD800 <= ord(c) <= 0xDFFF))
            clean_name = clean_text.strip(" \t\n\r🤩✨💎👑🍿🤖🛡️🎮🎁✈️💬🎵🎨📁📦🔴")
            if not clean_name:
                clean_name = "Premium Category"
            return clean_name, fallback_char, custom_id

    # If no custom emoji entities, check if text starts with standard emoji
    clean_text = "".join(c for c in raw_text if not (0xD800 <= ord(c) <= 0xDFFF))
    clean_name = clean_text.strip()
    for standard_emoji in ["🍿", "🤖", "🛡️", "🎮", "🎁", "✈️", "💬", "🎵", "🎨", "📁", "👑", "✨", "💎", "📦", "🔴"]:
        if clean_name.startswith(standard_emoji):
            fallback_char = standard_emoji
            clean_name = clean_name[len(standard_emoji):].strip()
            break

    return clean_name or "New Item", fallback_char, None

def extract_emoji_and_custom_id(message) -> tuple[str, Optional[str]]:
    """
    Backwards compatibility alias.
    Returns (fallback_emoji, custom_emoji_id).
    """
    _, fallback, custom_id = extract_clean_name_and_emoji(message)
    return fallback, custom_id

def text_to_tg_html(message) -> str:
    """
    Automatically converts any message containing Telegram Premium custom emojis
    into standard Telegram HTML with <tg-emoji> tags using UTF-16 code unit offsets.
    The admin only types normally with emojis — the bot handles all ID extraction and HTML tag generation!
    """
    if not message:
        return ""
    text = getattr(message, "text", "") or getattr(message, "caption", "") or ""
    entities = getattr(message, "entities", None) or getattr(message, "caption_entities", None) or []
    if not text or not entities:
        return text.strip()

    utf16_bytes = text.encode("utf-16-le")
    custom_entities = sorted(
        [e for e in entities if getattr(e, "type", "") == "custom_emoji" and getattr(e, "custom_emoji_id", None)],
        key=lambda e: e.offset,
        reverse=True
    )
    if not custom_entities:
        return text.strip()

    for ent in custom_entities:
        start_byte = ent.offset * 2
        end_byte = (ent.offset + ent.length) * 2
        fallback_bytes = utf16_bytes[start_byte:end_byte]
        try:
            fallback_char = fallback_bytes.decode("utf-16-le")
        except Exception:
            fallback_char = "✨"
        fallback_char = "".join(c for c in fallback_char if not (0xD800 <= ord(c) <= 0xDFFF)) or "✨"
        replacement = f'<tg-emoji emoji-id="{ent.custom_emoji_id}">{fallback_char}</tg-emoji>'
        replacement_bytes = replacement.encode("utf-16-le")
        utf16_bytes = utf16_bytes[:start_byte] + replacement_bytes + utf16_bytes[end_byte:]

    return utf16_bytes.decode("utf-16-le").strip()

def get_message_html_text(message) -> str:
    """
    Returns message text formatted with <tg-emoji> tags if custom emojis are present.
    """
    return text_to_tg_html(message)

def clean_button_text(html_text: str) -> str:
    """
    Strips HTML tags like <tg-emoji> AND leading/trailing decorative emojis
    to ensure button labels are clean without duplicate emojis when icon_custom_emoji_id is used.
    """
    if not html_text:
        return ""
    clean = re.sub(r'<[^>]+>', '', html_text)
    clean = "".join(c for c in clean if not (0xD800 <= ord(c) <= 0xDFFF))
    for char in [
        "👑", "🍿", "🤖", "🛡️", "🎓", "🎮", "🎁", "✈️", "💬", "🎵", "🎨", "📁", "📦",
        "🔴", "🌟", "🍏", "📺", "🍥", "✂️", "🧠", "⚡", "👨‍💻", "🔍", "🏠", "◀️", "▶️",
        "•", "✦", "★", "◈", "✔", "➜", "🤩", "❤️", "✨", "💎", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"
    ]:
        clean = clean.strip()
        if clean.startswith(char):
            clean = clean[len(char):].strip()
        if clean.endswith(char):
            clean = clean[:-len(char)].strip()
    return clean.strip()

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
