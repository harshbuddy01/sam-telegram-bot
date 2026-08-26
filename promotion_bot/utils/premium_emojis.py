class PremiumEmojis:
    # High-trust UI Accents
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
    FLASH = "5807506103063286427"
    WARNING = "5879753496000991296"

    # Services / Brands
    NETFLIX = "5039557485157942342"
    PRIME = "5807468522099447358"
    YOUTUBE = "5807506103063286427"
    SPOTIFY = "5868508172108435919"
    CHATGPT = "5796283422238314412"
    CLAUDE = "5364075889669718872"
    CANVA = "6257949774712932243"

EMOJI_SHORTCODES = {
    ":crown:": (PremiumEmojis.CROWN, "👑"),
    ":star:": (PremiumEmojis.STAR, "⭐"),
    ":fire:": (PremiumEmojis.FIRE, "🔥"),
    ":diamond:": (PremiumEmojis.DIAMOND, "💎"),
    ":sparkles:": (PremiumEmojis.SPARKLE, "✨"),
    ":verified:": (PremiumEmojis.VERIFIED, "✔️"),
    ":check:": (PremiumEmojis.CHECK, "✅"),
    ":gift:": (PremiumEmojis.GIFT, "🎁"),
    ":trophy:": (PremiumEmojis.TROPHY, "🏆"),
    ":netflix:": (PremiumEmojis.NETFLIX, "🎬"),
    ":prime:": (PremiumEmojis.PRIME, "📦"),
    ":youtube:": (PremiumEmojis.YOUTUBE, "▶️"),
    ":spotify:": (PremiumEmojis.SPOTIFY, "🎵"),
    ":chatgpt:": (PremiumEmojis.CHATGPT, "🤖"),
    ":claude:": (PremiumEmojis.CLAUDE, "🧠"),
}

def format_custom_emoji(document_id: str, fallback_emoji: str) -> str:
    """
    Returns the HTML tag for Telegram Premium custom emoji
    """
    return f'<tg-emoji emoji-id="{document_id}">{fallback_emoji}</tg-emoji>'

def parse_shortcodes_to_tg_emoji(text: str) -> str:
    """
    Replaces shortcodes like :crown:, :fire:, :diamond: with their proper <tg-emoji> tags
    """
    if not text:
        return text
    
    result = text
    for code, (doc_id, fallback) in EMOJI_SHORTCODES.items():
        if code in result:
            tag = format_custom_emoji(doc_id, fallback)
            result = result.replace(code, tag)
            
    return result
