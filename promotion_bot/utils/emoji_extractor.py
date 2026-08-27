from aiogram.types import Message, MessageEntity


def extract_html_with_premium_emojis(message: Message) -> str:
    """Extracts raw HTML text from an incoming Aiogram message, preserving:

    1. Native Telegram Premium Custom Emojis as <tg-emoji emoji-id="12345">emoji</tg-emoji>
    2. Bold (<b>), Italic (<i>), Underline (<u>), Strikethrough (<s>), Code (<code>), Pre (<pre>), Blockquote (<blockquote>)
    3. Hyperlinks (<a href="...">)
    """
    raw_text = message.text or message.caption or ""
    if not raw_text:
        return ""

    entities = message.entities or message.caption_entities or []
    if not entities:
        return raw_text

    # Convert UTF-16 code units (Telegram's offset standard) to UTF-16 representation
    utf16_text = raw_text.encode("utf-16-le")

    # Map of UTF-16 offset -> list of opening/closing tags
    # We collect insert operations
    inserts: list[tuple[int, int, str]] = []  # (offset_utf16_units, priority, tag_string)
    # priority: closing tags first (0), opening tags second (1)

    for ent in entities:
        start_u16 = ent.offset
        end_u16 = ent.offset + ent.length

        if ent.type == "custom_emoji" and getattr(ent, "custom_emoji_id", None):
            open_tag = f'<tg-emoji emoji-id="{ent.custom_emoji_id}">'
            close_tag = '</tg-emoji>'
            inserts.append((start_u16, 1, open_tag))
            inserts.append((end_u16, 0, close_tag))
        elif ent.type == "bold":
            inserts.append((start_u16, 1, "<b>"))
            inserts.append((end_u16, 0, "</b>"))
        elif ent.type == "italic":
            inserts.append((start_u16, 1, "<i>"))
            inserts.append((end_u16, 0, "</i>"))
        elif ent.type == "underline":
            inserts.append((start_u16, 1, "<u>"))
            inserts.append((end_u16, 0, "</u>"))
        elif ent.type == "strikethrough":
            inserts.append((start_u16, 1, "<s>"))
            inserts.append((end_u16, 0, "</s>"))
        elif ent.type == "code":
            inserts.append((start_u16, 1, "<code>"))
            inserts.append((end_u16, 0, "</code>"))
        elif ent.type == "pre":
            inserts.append((start_u16, 1, "<pre>"))
            inserts.append((end_u16, 0, "</pre>"))
        elif ent.type == "blockquote":
            inserts.append((start_u16, 1, "<blockquote>"))
            inserts.append((end_u16, 0, "</blockquote>"))
        elif ent.type == "text_link" and getattr(ent, "url", None):
            inserts.append((start_u16, 1, f'<a href="{ent.url}">'))
            inserts.append((end_u16, 0, "</a>"))

    if not inserts:
        return raw_text

    # Sort inserts: by offset ascending; for same offset, closing tags (0) before opening tags (1)
    inserts.sort(key=lambda x: (x[0], x[1]))

    # Reconstruct text by slicing UTF-16 bytes
    result_pieces = []
    curr_u16 = 0

    for offset_u16, _, tag in inserts:
        if offset_u16 > curr_u16:
            chunk = utf16_text[curr_u16 * 2 : offset_u16 * 2].decode("utf-16-le", errors="ignore")
            result_pieces.append(chunk)
            curr_u16 = offset_u16
        result_pieces.append(tag)

    if curr_u16 * 2 < len(utf16_text):
        chunk = utf16_text[curr_u16 * 2 :].decode("utf-16-le", errors="ignore")
        result_pieces.append(chunk)

    return "".join(result_pieces)
