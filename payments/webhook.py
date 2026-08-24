import json
import logging
import os
import aiohttp
from aiohttp import web
from aiogram import Bot
from sqlalchemy import select

from database.database import AsyncSessionLocal
from database.models import Deposit
from database.crud import (
    get_user,
    get_variant,
    get_product,
    fulfill_order,
    create_manual_order,
    credit_user_deposit_automated,
    get_available_stock_count
)
from payments.manager import payment_manager
from utils.emojis import CustomEmojis, ce, UI
from utils.notifications import send_order_notification
from keyboards.user_keyboards import get_post_delivery_keyboard
import config

logger = logging.getLogger(__name__)

async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "healthy",
        "service": "SamStore Telegram Sales Bot",
        "gateways": {
            "razorpay": payment_manager.razorpay.is_configured,
            "cashfree": payment_manager.cashfree.is_configured
        }
    })

async def handle_root(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "message": "SamStore Webhook Server is running"
    })

async def handle_razorpay_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    body_bytes = await request.read()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # 1. Verify signature if webhook secret configured
    if not payment_manager.razorpay.verify_webhook_signature(body_bytes, signature):
        logger.warning("Razorpay webhook signature verification failed!")
        return web.Response(status=400, text="Invalid signature")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse Razorpay webhook JSON: {e}")
        return web.Response(status=400, text="Bad JSON")

    event = payload.get("event", "")
    logger.info(f"Received Razorpay Webhook Event: {event}")

    # Process events
    if event in ("payment_link.paid", "payment.captured", "order.paid", "qr_code.credited", "qr_code.closed"):
        plink_data = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
        payment_data = payload.get("payload", {}).get("payment", {}).get("entity", {})
        qr_data = payload.get("payload", {}).get("qr_code", {}).get("entity", {})
        
        # For QR code events, the qr_code ID is the gateway_order_id
        qr_id = qr_data.get("id")
        plink_id = plink_data.get("id") or payment_data.get("order_id") or payment_data.get("id")
        payment_id = payment_data.get("id", "")
        reference_id = plink_data.get("reference_id")
        
        # Extract notes from whichever entity has them
        notes = qr_data.get("notes") or plink_data.get("notes") or payment_data.get("notes") or {}
        if isinstance(notes, list):
            notes = {}
        user_id_str = notes.get("user_id")
        
        # The ID to match in our deposits table
        match_id = qr_id or plink_id
        
        async with AsyncSessionLocal() as session:
            deposit = None
            
            # Match deposit by qr_id or plink_id
            if match_id:
                stmt = select(Deposit).where(Deposit.gateway_order_id == match_id)
                res = await session.execute(stmt)
                deposit = res.scalar_one_or_none()
            
            # If QR event, also try matching by plink_id
            if not deposit and plink_id and plink_id != match_id:
                stmt = select(Deposit).where(Deposit.gateway_order_id == plink_id)
                res = await session.execute(stmt)
                deposit = res.scalar_one_or_none()
                
            # Fallback match by user_id + PENDING status
            if not deposit and user_id_str:
                try:
                    uid = int(user_id_str)
                    stmt = select(Deposit).where(Deposit.user_id == uid, Deposit.status == "PENDING").order_by(Deposit.created_at.desc())
                    res = await session.execute(stmt)
                    deposit = res.scalar_one_or_none()
                except Exception:
                    pass

            if not deposit:
                logger.info(f"No pending deposit matching gateway_order_id={match_id} or plink={plink_id} or user={user_id_str}")
                return web.json_response({"status": "ignored_no_match"})

            # Idempotency check: Already processed
            if deposit.status in ("APPROVED", "SUCCESS"):
                logger.info(f"Deposit #{deposit.id} already processed. Skipping duplicate webhook.")
                return web.json_response({"status": "already_processed"})

            # Process & Credit Deposit
            deposit, user = await credit_user_deposit_automated(session, deposit.gateway_order_id or plink_id, payment_id)
            if not deposit or not user:
                return web.json_response({"status": "credit_failed"})

            logger.info(f"Deposit #{deposit.id} successfully credited via webhook for User {user.telegram_id} (Amount: ₹{deposit.amount})")            # Check if this was a Direct 1-Click Purchase
            if deposit.target_variant_id:
                target_var = await get_variant(session, deposit.target_variant_id)
                if target_var:
                    is_manual = (getattr(target_var, "fulfillment_type", "AUTOMATIC") == "MANUAL")
                    prod = await get_product(session, target_var.product_id)
                    prod_title = prod.title if prod else "Digital Item"
                    
                    order = None
                    if not is_manual:
                        order, err = await fulfill_order(session, user.telegram_id, target_var.id, target_var.price)
                    
                    # If auto fulfillment worked
                    if order and getattr(order, "delivered_content", None):
                        delivery_text = (
                            f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & ORDER DELIVERED!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{ce(CustomEmojis.KEY, '🔑')} <b>YOUR DELIVERED ACCOUNT / CODE:</b>\n"
                            f"<i>(Tap the box below to copy automatically)</i>\n\n"
                            f"<pre><code>{order.delivered_content}</code></pre>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Full Warranty:</b> Covered throughout validity!\n"
                            f"{ce(CustomEmojis.HEART, '❤️')} <i>Thank you for shopping with {config.STORE_NAME}!</i>"
                        )
                        kb = get_post_delivery_keyboard(order.id)
                        try:
                            await bot.send_message(user.telegram_id, delivery_text, reply_markup=kb)
                        except Exception as e:
                            logger.error(f"Failed to send delivery to user {user.telegram_id}: {e}")

                        # Group/Channel Notification
                        remaining = await get_available_stock_count(session, target_var.id)
                        bot_me = await bot.me()
                        await send_order_notification(
                            bot=bot,
                            order_id=order.id,
                            buyer_name=user.full_name or "Customer",
                            product_title=prod_title,
                            variant_name=target_var.name,
                            amount=order.amount,
                            stock_left=remaining,
                            bot_username=bot_me.username or ""
                        )
                        
                        # Alert Admins
                        admin_alert = (
                            f"{ce(CustomEmojis.FIRE, '🔔')} <b>WEBHOOK AUTO-DELIVERED SALE!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
                            f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
                            f"{ce(CustomEmojis.KEY, '🆔')} <b>User ID:</b> <code>{user.telegram_id}</code>\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {target_var.name}\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f} (Razorpay)\n"
                            f"{ce(CustomEmojis.TROPHY, '📊')} <b>Remaining Stock:</b> {remaining} available"
                        )
                        for admin_id in config.ADMIN_IDS:
                            try:
                                await bot.send_message(admin_id, admin_alert)
                            except Exception:
                                pass

                        return web.json_response({"status": "delivered_auto"})
                    
                    else:
                        # MANUAL FULFILLMENT or STOCK EMPTY -> Create manual order
                        manual_order = await create_manual_order(session, user.telegram_id, target_var.id, target_var.price, customer_input=None)
                        
                        manual_confirm_text = (
                            f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & ORDER PLACED!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{manual_order.id}\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{manual_order.amount:.2f}</b>\n"
                            f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Estimated Delivery:</b> 1–2 Hours\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Our team has received your order and is processing your invitation/activation right now! You will receive your details directly in this chat shortly."
                        )
                        try:
                            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                            kb = InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🛟 Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}")],
                                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
                            ])
                            await bot.send_message(user.telegram_id, manual_confirm_text, reply_markup=kb)
                        except Exception as e:
                            logger.error(f"Failed to send manual confirm to user {user.telegram_id}: {e}")

                        # Notify Group
                        remaining = await get_available_stock_count(session, target_var.id)
                        bot_me = await bot.me()
                        await send_order_notification(
                            bot=bot,
                            order_id=manual_order.id,
                            buyer_name=user.full_name or "Customer",
                            product_title=prod_title,
                            variant_name=target_var.name,
                            amount=manual_order.amount,
                            stock_left=remaining,
                            bot_username=bot_me.username or ""
                        )

                        # Alert Admins with Fulfill Button
                        from keyboards.admin_keyboards import get_admin_order_actions_keyboard
                        admin_manual_alert = (
                            f"{ce(CustomEmojis.FIRE, '🚨')} <b>NEW 1-CLICK PAID ORDER TO FULFILL!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{manual_order.id}\n"
                            f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
                            f"{ce(CustomEmojis.KEY, '🆔')} <b>User ID:</b> <code>{user.telegram_id}</code>\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {target_var.name}\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Paid:</b> {config.CURRENCY_SYMBOL}{manual_order.amount:.2f} (Razorpay)\n\n"
                            f"{ce(CustomEmojis.SPARKLE, '👉')} <i>Click 'Fulfill Order' below to send invite/credentials:</i>"
                        )
                        for admin_id in config.ADMIN_IDS:
                            try:
                                await bot.send_message(admin_id, admin_manual_alert, reply_markup=get_admin_order_actions_keyboard(manual_order.id))
                            except Exception:
                                pass

                        return web.json_response({"status": "placed_manual"})

            # Normal Top-Up Deposit notification to user
            deposit_msg = (
                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & CREDITED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Added:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
                f"{ce(CustomEmojis.CARD, '💳')} <b>New Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
                f"You can now purchase any subscription instantly from the store!"
            )
            try:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛍️ Explore Store", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                ])
                await bot.send_message(user.telegram_id, deposit_msg, reply_markup=kb)
            except Exception as e:
                logger.error(f"Failed to notify user of deposit: {e}")

            # Notify Admin of Deposit
            admin_dep_alert = (
                f"{ce(CustomEmojis.FIRE, '🔔')} <b>AUTO-DEPOSIT CAPTURED VIA RAZORPAY!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
                f"{ce(CustomEmojis.VERIFIED, '👤')} <b>User:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
                f"{ce(CustomEmojis.KEY, '🔢')} <b>Payment ID:</b> <code>{payment_id or 'Auto'}</code>"
            )
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_dep_alert)
                except Exception:
                    pass

async def handle_razorpay_webhook_get(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "message": "Razorpay Webhook endpoint is active and listening for POST payment events."
    })

def create_webhook_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/webhook/razorpay", handle_razorpay_webhook_get)
    app.router.add_post("/webhook/razorpay", handle_razorpay_webhook)
    return app
