import asyncio
import logging
import datetime
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import config
from database.database import AsyncSessionLocal
from database.models import Order, Variant, Product
from database.crud import get_available_stock_count
from utils.validity import get_order_validity_info
from utils.emojis import CustomEmojis, ce, format_emoji, Emojis

logger = logging.getLogger("expiry_notifier")

async def check_and_send_expiry_reminders(bot: Bot):
    """Scans active orders and sends pre-expiry and expired reminders."""
    now = datetime.datetime.utcnow()
    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(Order)
                .options(selectinload(Order.variant).selectinload(Variant.product))
                .where(
                    Order.status.in_(["COMPLETED", "DELIVERED"]),
                    Order.expiry_notified_stage < 3
                )
            )
            result = await session.execute(stmt)
            orders = result.scalars().all()

            for order in orders:
                try:
                    if not order.variant:
                        continue

                    variant = order.variant
                    product = variant.product
                    prod_title = product.title if product else "Digital Item"
                    var_name = variant.name
                    info = get_order_validity_info(order, now=now)
                    days_remaining = info["days_remaining"]
                    is_expired = info["is_expired"]
                    expiry_str = info["expiry_short"]
                    purchased_str = order.created_at.strftime("%d %b %Y")

                    current_stage = getattr(order, "expiry_notified_stage", 0) or 0
                    should_notify = False
                    new_stage = current_stage
                    msg_text = ""

                    # Check stock for renewal button
                    stock_count = await get_available_stock_count(session, variant.id)
                    is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")
                    can_order = (stock_count > 0) or is_manual

                    if can_order:
                        renew_btn = InlineKeyboardButton(
                            text=f"🔄 Renew & Continue Plan ({config.CURRENCY_SYMBOL}{variant.price:.0f})",
                            callback_data=f"buy_{variant.id}",
                            icon_custom_emoji_id=CustomEmojis.FIRE
                        )
                    else:
                        support_url = (
                            f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}?"
                            f"text=Hi! I want to renew Order #{order.id} ({prod_title} - {var_name}), "
                            f"but it is out of stock. When will it be available?"
                        )
                        renew_btn = InlineKeyboardButton(
                            text="🛟 Out of Stock — Contact Support",
                            url=support_url,
                            icon_custom_emoji_id=CustomEmojis.SUPPORT
                        )

                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [renew_btn],
                        [
                            InlineKeyboardButton(text="🛍️ Explore Store", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP),
                            InlineKeyboardButton(text="📜 My Orders", callback_data="view_orders", icon_custom_emoji_id=CustomEmojis.ORDERS)
                        ]
                    ])

                    # Stage 1: 5-Day Reminder
                    if not is_expired and days_remaining <= 5 and days_remaining > 2 and current_stage < 1:
                        should_notify = True
                        new_stage = 1
                        msg_text = (
                            f"{ce(CustomEmojis.FIRE, '🔔')} <b>SUBSCRIPTION EXPIRING SOON!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"Dear Customer, your subscription access is nearing its renewal date:\n\n"
                            f"<blockquote>"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> <code>#{order.id}</code>\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{var_name}</b>\n"
                            f"{ce(CustomEmojis.STAR, '📅')} <b>Purchased On:</b> {purchased_str}\n"
                            f"{ce(CustomEmojis.DIAMOND, '⏳')} <b>Expiration Date:</b> <b>{expiry_str} ({days_remaining} days left)</b>"
                            f"</blockquote>\n\n"
                            f"To keep your personal profile, watch history, and stream uninterrupted, renew your subscription early! Tap below to renew in 1 click:"
                        )

                    # Stage 2: 2-Day Final Reminder
                    elif not is_expired and days_remaining <= 2 and current_stage < 2:
                        should_notify = True
                        new_stage = 2
                        hours_left = info["hours_remaining"]
                        countdown_str = f"{hours_left} hours" if days_remaining == 0 else f"{days_remaining} days"
                        msg_text = (
                            f"{ce(CustomEmojis.LOCK, '⚠️')} <b>FINAL REMINDER: SUBSCRIPTION EXPIRING!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"Heads up! Only <b>{countdown_str}</b> remaining on your subscription:\n\n"
                            f"<blockquote>"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> <code>#{order.id}</code>\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{var_name}</b>\n"
                            f"{ce(CustomEmojis.DIAMOND, '⏳')} <b>Expires:</b> <b>{expiry_str} ({countdown_str} left)</b>"
                            f"</blockquote>\n\n"
                            f"Avoid sudden interruption! Tap below to renew and continue your plan seamlessly:"
                        )

                    # Stage 3: Expired Notice
                    elif is_expired and current_stage < 3:
                        should_notify = True
                        new_stage = 3
                        msg_text = (
                            f"{ce(CustomEmojis.LOCK, '🔴')} <b>YOUR SUBSCRIPTION HAS EXPIRED</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"Your subscription validity for <b>{prod_title} — {var_name}</b> (Order <code>#{order.id}</code>) has concluded on {expiry_str}.\n\n"
                            f"If you wish to continue enjoying this service, you can reclaim and renew your plan right now:"
                        )

                    if should_notify and msg_text:
                        try:
                            await bot.send_message(order.user_id, msg_text, reply_markup=kb)
                            order.expiry_notified_stage = new_stage
                            await session.commit()
                            logger.info(f"Dispatched expiry reminder (stage {new_stage}) for order #{order.id} to user {order.user_id}")
                        except Exception as send_err:
                            logger.warning(f"Could not send reminder to {order.user_id}: {send_err}")
                except Exception as inner_err:
                    logger.error(f"Error checking order #{order.id}: {inner_err}")

    except Exception as e:
        logger.error(f"Error during expiry reminder scan: {e}")


async def start_expiry_reminder_scheduler(bot: Bot):
    """Background loop running every 2 hours."""
    logger.info("Starting background subscription expiry reminder service...")
    await asyncio.sleep(10)
    while True:
        try:
            await check_and_send_expiry_reminders(bot)
        except Exception as loop_err:
            logger.error(f"Scheduler loop error: {loop_err}")
        await asyncio.sleep(7200)
