import re
import random

SPINTAX_PATTERN = re.compile(r'\{([^{}]+)\}')
INVISIBLE_CHARS = ['\u200b', '\u200c', '\u200d', '\ufeff']

def process_spintax(text: str) -> str:
    """
    Recursively processes Spintax syntax like {Option 1|Option 2|Option 3}
    """
    if not text:
        return text
    
    while True:
        match = SPINTAX_PATTERN.search(text)
        if not match:
            break
        options = match.group(1).split('|')
        chosen = random.choice(options)
        text = text[:match.start()] + chosen + text[match.end():]
        
    return text

def add_anti_hash_jitter(text: str) -> str:
    """
    Appends invisible zero-width unicode characters to alter the MD5/SHA256 message hash
    without altering what human users see in Telegram.
    This prevents Telegram's spam filter from matching identical broadcast text across 300+ groups.
    """
    if not text:
        return text
    
    jitter_len = random.randint(1, 4)
    jitter = "".join(random.choice(INVISIBLE_CHARS) for _ in range(jitter_len))
    return text + jitter

def prepare_broadcast_message(text: str, apply_spintax: bool = True, apply_jitter: bool = True) -> str:
    """
    Generates a unique variation of the promotion text ready to send.
    """
    processed = text
    if apply_spintax:
        processed = process_spintax(processed)
    if apply_jitter:
        processed = add_anti_hash_jitter(processed)
    return processed
