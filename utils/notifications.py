"""
Group/Channel Notification Utilities
Sends order alerts, restock alerts, and handles username masking.
"""
import logging
from typing import Optional
from datetime import datetime
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from utils.emojis import CustomEmojis, ce, clean_button_text

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
        return name[0] + "*" if name else "User"
    return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"


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
    Post an order confirmation alert to the configured group/channel.
    Only sends if NOTIFICATION_CHANNEL_ID is set in config.
    """
    channel_id = config.NOTIFICATION_CHANNEL_ID
    if not channel_id:
        return

    masked = mask_username(buyer_name)
    now_str = datetime.now().strftime("%I:%M %p, %d %b %Y")
    clean_prod = clean_button_text(product_title) or "Product"
    clean_var = clean_button_text(variant_name) if variant_name else ""

    text = (
        f"{ce(CustomEmojis.FIRE, '🚨')} <b>NEW ORDER COMPLETED!</b> {ce(CustomEmojis.FIRE, '🚨')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{clean_prod}</b>\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Buyer:</b> <code>{masked}</code>\n"
        f"{ce(CustomEmojis.GIFT, '🎁')} <b>Variant:</b> {clean_var}\n"
        f"{ce(CustomEmojis.DIAMOND, '💎')} <b>Paid:</b> <b>{config.CURRENCY_SYMBOL}{amount:.1f}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Payment Mode:</b> Instant Auto-Fulfillment\n"
        f"{ce(CustomEmojis.FIRE, '🔥')} <b>Stock Left:</b> <code>{stock_left} in stock</code>\n"
        f"{ce(CustomEmojis.STAR, '📅')} <b>Time:</b> {now_str}\n\n"
        f"{ce(CustomEmojis.CHECK, '✅')} <i>Credentials securely delivered to buyer!</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = None
    if bot_username:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🛒 Buy {clean_prod} Now",
                url=f"https://t.me/{bot_username}?start=shop",
                icon_custom_emoji_id=CustomEmojis.SHOP
            )]
        ])

    try:
        await bot.send_message(channel_id, text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Failed to send order notification to channel {channel_id}: {e}")


async def send_restock_alert(
    bot: Bot,
    product_title: str,
    variant_name: str,
    added_count: int,
    total_stock: int,
    bot_username: str = "",
    product_id: Optional[int] = None,
    variant_id: Optional[int] = None
):
    """
    Post a restock alert to the configured group/channel with direct 1-click deep link.
    """
    channel_id = config.NOTIFICATION_CHANNEL_ID
    if not channel_id:
        return

    clean_prod = clean_button_text(product_title) or "Product"
    clean_var = clean_button_text(variant_name) if variant_name else ""

    plan_line = f"\n{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <code>{clean_var}</code>" if clean_var else ""
    text = (
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>RESTOCK ALERT — {clean_prod.upper()}!</b> {ce(CustomEmojis.SPARKLE, '🎉')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.FIRE, '🔥')} <b>{clean_prod}</b> is back in stock!{plan_line}\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Fresh Stock Added:</b> <code>+{added_count} unit(s)</code>\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Live Available Stock:</b> <code>{total_stock} unit(s)</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.SPARKLE, '👇')} <i>Click below to buy or view plan details with instant delivery:</i>"
    )

    kb = None
    if bot_username:
        if variant_id:
            target_url = f"https://t.me/{bot_username}?start=var_{variant_id}"
            btn_title = f"⚡ Buy Now • {clean_var or clean_prod}"
        elif product_id:
            target_url = f"https://t.me/{bot_username}?start=prod_{product_id}"
            btn_title = f"⚡ Buy Now • {clean_prod}"
        else:
            target_url = f"https://t.me/{bot_username}?start=shop"
            btn_title = f"⚡ Buy Now • {clean_prod}"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=btn_title,
                url=target_url,
                icon_custom_emoji_id=CustomEmojis.SHOP
            )]
        ])

    try:
        await bot.send_message(channel_id, text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Failed to send restock alert to channel {channel_id}: {e}")
