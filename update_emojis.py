import re
from pathlib import Path

def process_file(filepath):
    content = Path(filepath).read_text()
    
    # Add imports if missing
    if "from utils.emojis import Emojis, UI, format_emoji" in content:
        content = content.replace(
            "from utils.emojis import Emojis, UI, format_emoji",
            "from utils.emojis import Emojis, UI, format_emoji, CustomEmojis, ce"
        )
    elif "from utils.emojis import Emojis, UI" in content:
        content = content.replace(
            "from utils.emojis import Emojis, UI",
            "from utils.emojis import Emojis, UI, CustomEmojis, ce"
        )
        
    Path(filepath).write_text(content)

process_file('/Users/harshanand/Downloads/SAM TELEGRAM/handlers/start.py')
process_file('/Users/harshanand/Downloads/SAM TELEGRAM/handlers/order.py')
process_file('/Users/harshanand/Downloads/SAM TELEGRAM/handlers/wallet.py')
