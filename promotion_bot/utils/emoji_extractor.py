import html
from aiogram.types import Message


def extract_html_with_premium_emojis(message: Message) -> str:
    """Extracts clean HTML text from an incoming Aiogram message, preserving:

    1. Native Telegram Premium Custom Emojis as <tg-emoji emoji-id="12345">emoji</tg-emoji>
    2. Bold (<b>), Italic (<i>), Underline (<u>), Strikethrough (<s>), Code (<code>), Pre (<pre>), Blockquote (<blockquote>)
    3. Hyperlinks (<a href="...">)

    Uses Aiogram's built-in HtmlDecoration which guarantees valid tag nesting and proper escaping.
    """
    try:
        if hasattr(message, "html_text") and message.html_text:
            return message.html_text
    except Exception:
        pass

    raw_text = message.text or message.caption or ""
    return html.escape(raw_text)
