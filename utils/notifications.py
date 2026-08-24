"""
Group/Channel Notification Utilities
Sends order alerts, restock alerts, and handles username masking.
"""
import logging
from datetime import datetime
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from utils.emojis import CustomEmojis, ce

logger = logging.getLogger(__name__)


def mask_username(name: str) -> str:
    """
    Mask a username/name for public display.
    'harshanand' → 'h******nd'
    'john' → 'j**n'
    'ab' → 'a*'
    """
    if not name:
        return "Anonymous"
    name = name.strip()
    if len(name) <= 2:
        return name[0] + "*"
    elif len(name) <= 4:
        return name[0] + "*" * (len(name) - 2) + name[-1]
    else:
        return name[0] + "*" * (len(name) - 2) + name[-2:]


async def send_order_notification(
    bot: Bot,
    order_id: int,
    buyer_name: str,
    product_title: str,
    variant_name: str,
    amount: float,
    stock_left: int,
    bot_username: str = ""
):
    """
    Post an order notification to the configured group/channel.
    Matches the Quantum-xD style card with masked buyer name.
    """
    channel_id = config.NOTIFICATION_CHANNEL_ID
    if not channel_id:
        return

    masked_name = mask_username(buyer_name)
    now = datetime.utcnow()
    time_str = now.strftime("%I:%M %p, %d %b %Y")

    stock_text = f"Only {stock_left} remaining!" if stock_left <= 10 else f"{stock_left} in stock"

    text = (
        f"{ce(CustomEmojis.SHOP, '📦')} <b>New Order Received!</b> {ce(CustomEmojis.SHOP, '📦')}\n\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Buyer:</b> <code>{masked_name}</code>\n"
        f"{ce(CustomEmojis.GIFT, '🎁')} <b>Product:</b> {product_title}\n"
        f"{ce(CustomEmojis.DIAMOND, '💎')} <b>Variant:</b> {variant_name}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Paid Amount:</b> {config.CURRENCY_SYMBOL}{amount:.2f}\n"
        f"{ce(CustomEmojis.FIRE, '🔥')} <b>Stock Left:</b> {stock_text}\n"
        f"{ce(CustomEmojis.STAR, '📅')} <b>Time:</b> {time_str}\n\n"
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Thank you for choosing us!</b>"
    )

    # Deep-link button to the bot
    kb = None
    if bot_username:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Buy Now", url=f"https://t.me/{bot_username}?start=shop")]
        ])

    try:
        await bot.send_message(channel_id, text, reply_markup=kb)
    except Exception as e:
        logger.warning(f"Failed to send order notification to channel {channel_id}: {e}")


async def send_restock_alert(
    bot: Bot,
    product_title: str,
    variant_name: str,
    added_count: int,
    total_stock: int,
    bot_username: str = ""
):
    """
    Post a restock alert to the configured group/channel.
    """
    channel_id = config.NOTIFICATION_CHANNEL_ID
    if not channel_id:
        return

    text = (
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>RESTOCK ALERT: {product_title.upper()}</b> {ce(CustomEmojis.SPARKLE, '🎉')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.FIRE, '🔥')} We have just added <b>{added_count} new stock</b> for {product_title}!\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Current Total Stock:</b> <code>{total_stock} unit(s)</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.SPARKLE, '👇')} Click the button below to buy or view details instantly:"
    )

    kb = None
    if bot_username:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🎁 {product_title} • {total_stock} Available",
                url=f"https://t.me/{bot_username}?start=shop"
            )]
        ])

    try:
        await bot.send_message(channel_id, text, reply_markup=kb)
    except Exception as e:
        logger.warning(f"Failed to send restock alert to channel {channel_id}: {e}")
