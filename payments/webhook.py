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
            "paypal": payment_manager.paypal.is_configured,
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
                    qty = max(1, int(round(deposit.amount / target_var.price))) if target_var.price > 0 else 1
                    if not is_manual:
                        order, err = await fulfill_order(session, user.telegram_id, target_var.id, target_var.price, quantity=qty)
                    
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

                        # Alert Admins (broadcast deferred to user's "I Got It!" confirmation)
                        remaining = await get_available_stock_count(session, target_var.id)
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
                        requires_input = getattr(target_var, "requires_customer_input", True)
                        dispatch_time = getattr(target_var, "manual_dispatch_time", "1–2 Hours") or "1–2 Hours"

                        if requires_input:
                            manual_order, m_err = await create_manual_order(
                                session,
                                user.telegram_id,
                                target_var.id,
                                target_var.price,
                                customer_input="Awaiting customer details...",
                                quantity=qty
                            )
                            dp = request.app.get("dp")
                            if dp and hasattr(dp, "storage"):
                                from aiogram.fsm.context import FSMContext
                                from aiogram.fsm.storage.base import StorageKey
                                from utils.states import OrderManualStates
                                fsm_state = FSMContext(
                                    storage=dp.storage,
                                    key=StorageKey(bot_id=bot.id, chat_id=user.telegram_id, user_id=user.telegram_id)
                                )
                                await fsm_state.set_state(OrderManualStates.waiting_for_input)
                                await fsm_state.update_data(
                                    order_id=manual_order.id,
                                    variant_id=target_var.id,
                                    price=target_var.price,
                                    quantity=qty,
                                    prod_title=prod_title,
                                    var_name=target_var.name,
                                    dispatch_time=dispatch_time,
                                    is_paid=True
                                )

                            prompt_msg = getattr(target_var, "input_prompt", None) or "Please send your target Email / Account username for activation:"
                            qty_line = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""
                            manual_confirm_text = (
                                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED! (Order #{manual_order.id})</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>ACTIVATION DETAILS REQUIRED</b>\n\n"
                                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>{qty_line}\n"
                                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{manual_order.amount:.2f}</b>\n"
                                f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Delivery Time:</b> within {dispatch_time}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.SPARKLE, '👉')} <b>{prompt_msg}</b>\n\n"
                                f"<i>(Reply to this message with your details so our team can activate your service!)</i>"
                            )
                            try:
                                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
                                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                                ])
                                await bot.send_message(user.telegram_id, manual_confirm_text, reply_markup=kb)
                            except Exception as e:
                                logger.error(f"Failed to send manual confirm to user {user.telegram_id}: {e}")

                            return web.json_response({"status": "manual_order_pending_details"})
                        else:
                            manual_order, m_err = await create_manual_order(
                                session,
                                user.telegram_id,
                                target_var.id,
                                target_var.price,
                                customer_input=None,
                                quantity=qty
                            )
                            qty_line = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""
                            manual_confirm_text = (
                                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & ORDER PLACED!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{manual_order.id}\n"
                                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>{qty_line}\n"
                                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{manual_order.amount:.2f}</b>\n"
                                f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Estimated Delivery:</b> within {dispatch_time}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"Our team has received your order and is preparing your credentials right now! You will receive your details directly in this chat shortly."
                            )
                            try:
                                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
                                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                                ])
                                await bot.send_message(user.telegram_id, manual_confirm_text, reply_markup=kb)
                            except Exception as e:
                                logger.error(f"Failed to send manual confirm to user {user.telegram_id}: {e}")

                            # Alert Admins with Fulfill Button
                            from handlers.order import _background_notify_manual
                            import asyncio
                            asyncio.create_task(_background_notify_manual(
                                bot, manual_order, prod_title, target_var.name, user, None, manual_order.amount, qty
                            ))
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
                    [InlineKeyboardButton(text="Explore Store", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
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

            return web.json_response({"status": "credited_deposit"})

    # Always return 200 OK for any unhandled events like qr_code.created, payment.authorized, etc.
    return web.json_response({"status": f"ignored_event_{event}"})

async def handle_razorpay_webhook_get(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "message": "Razorpay Webhook endpoint is active and listening for POST payment events."
    })

async def handle_paypal_webhook_get(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "message": "PayPal Webhook endpoint is active and listening for POST payment events."
    })

async def handle_paypal_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    body_bytes = await request.read()

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse PayPal webhook JSON: {e}")
        return web.Response(status=400, text="Bad JSON")

    event_type = payload.get("event_type", "")
    resource = payload.get("resource", {})
    logger.info(f"Received PayPal Webhook Event: {event_type}")

    # Relevant event types: CHECKOUT.ORDER.APPROVED, PAYMENT.CAPTURE.COMPLETED, CHECKOUT.ORDER.COMPLETED
    if event_type in ("CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED", "CHECKOUT.ORDER.COMPLETED"):
        paypal_order_id = resource.get("id")
        capture_id = resource.get("id") if event_type == "PAYMENT.CAPTURE.COMPLETED" else ""
        
        # If it's a capture event, the order id may be inside supplementary_data
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            supp = resource.get("supplementary_data", {}).get("related_ids", {})
            if supp.get("order_id"):
                paypal_order_id = supp.get("order_id")

        custom_id = resource.get("custom_id")
        if not custom_id and "purchase_units" in resource:
            pu = resource["purchase_units"]
            if isinstance(pu, list) and len(pu) > 0:
                custom_id = pu[0].get("custom_id") or pu[0].get("reference_id")

        async with AsyncSessionLocal() as session:
            deposit = None
            if paypal_order_id:
                stmt = select(Deposit).where(Deposit.gateway_order_id == paypal_order_id)
                res = await session.execute(stmt)
                deposit = res.scalar_one_or_none()

            # Fallback by custom_id (user_id) if not found by paypal_order_id
            if not deposit and custom_id:
                try:
                    uid = int(str(custom_id).replace("BUY", "").replace("DEP", "").split("_")[0])
                    stmt = select(Deposit).where(Deposit.user_id == uid, Deposit.status == "PENDING", Deposit.gateway == "PAYPAL").order_by(Deposit.created_at.desc())
                    res = await session.execute(stmt)
                    deposit = res.scalar_one_or_none()
                except Exception:
                    pass

            if not deposit:
                logger.info(f"PayPal webhook: No matching pending deposit found for order={paypal_order_id}, custom_id={custom_id}")
                return web.json_response({"status": "ignored_no_match"})

            # Idempotency check
            if deposit.status in ("APPROVED", "SUCCESS"):
                logger.info(f"Deposit #{deposit.id} already approved. Skipping duplicate webhook.")
                return web.json_response({"status": "already_processed"})

            # Cross-verify payment capture with PayPal API to prevent unauthenticated/forged requests
            status_res = await payment_manager.paypal.verify_payment_status(deposit.gateway_order_id)
            if not status_res.get("is_paid"):
                logger.warning(f"PayPal verification failed for deposit #{deposit.id}: {status_res}")
                return web.json_response({"status": "verification_failed"}, status=400)
            capture_id = status_res.get("capture_id") or capture_id

            # Process & Credit Deposit
            deposit, user = await credit_user_deposit_automated(session, deposit.gateway_order_id, capture_id or "PAYPAL_AUTO")
            if not deposit or not user:
                return web.json_response({"status": "credit_failed"})

            logger.info(f"Deposit #{deposit.id} successfully credited via PayPal webhook for User {user.telegram_id} (Amount: ₹{deposit.amount})")

            # Check if this was a Direct 1-Click Purchase
            if deposit.target_variant_id:
                target_var = await get_variant(session, deposit.target_variant_id)
                if target_var:
                    is_manual = (getattr(target_var, "fulfillment_type", "AUTOMATIC") == "MANUAL")
                    prod = await get_product(session, target_var.product_id)
                    prod_title = prod.title if prod else "Digital Item"

                    order = None
                    qty = max(1, int(round(deposit.amount / target_var.price))) if target_var.price > 0 else 1
                    if not is_manual:
                        order, err = await fulfill_order(session, user.telegram_id, target_var.id, target_var.price, quantity=qty)

                    if order and getattr(order, "delivered_content", None):
                        delivery_text = (
                            f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & ORDER DELIVERED!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b> (via PayPal)\n\n"
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

                        # Alert Admins (broadcast deferred to user's "I Got It!" confirmation)
                        remaining = await get_available_stock_count(session, target_var.id)
                        admin_alert = (
                            f"{ce(CustomEmojis.FIRE, '🔔')} <b>PAYPAL AUTO-DELIVERED SALE!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
                            f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
                            f"{ce(CustomEmojis.KEY, '🆔')} <b>User ID:</b> <code>{user.telegram_id}</code>\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {target_var.name}\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f} (PayPal)\n"
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
                        requires_input = getattr(target_var, "requires_customer_input", True)
                        dispatch_time = getattr(target_var, "manual_dispatch_time", "1–2 Hours") or "1–2 Hours"

                        if requires_input:
                            manual_order, m_err = await create_manual_order(
                                session,
                                user.telegram_id,
                                target_var.id,
                                target_var.price,
                                customer_input="Awaiting customer details...",
                                quantity=qty
                            )
                            dp = request.app.get("dp")
                            if dp and hasattr(dp, "storage"):
                                from aiogram.fsm.context import FSMContext
                                from aiogram.fsm.storage.base import StorageKey
                                from utils.states import OrderManualStates
                                fsm_state = FSMContext(
                                    storage=dp.storage,
                                    key=StorageKey(bot_id=bot.id, chat_id=user.telegram_id, user_id=user.telegram_id)
                                )
                                await fsm_state.set_state(OrderManualStates.waiting_for_input)
                                await fsm_state.update_data(
                                    order_id=manual_order.id,
                                    variant_id=target_var.id,
                                    price=target_var.price,
                                    quantity=qty,
                                    prod_title=prod_title,
                                    var_name=target_var.name,
                                    dispatch_time=dispatch_time,
                                    is_paid=True
                                )

                            prompt_msg = getattr(target_var, "input_prompt", None) or "Please send your target Email / Account username for activation:"
                            qty_line = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""
                            manual_confirm_text = (
                                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED! (Order #{manual_order.id})</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>ACTIVATION DETAILS REQUIRED</b>\n\n"
                                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>{qty_line}\n"
                                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{manual_order.amount:.2f}</b>\n"
                                f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Delivery Time:</b> within {dispatch_time}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.SPARKLE, '👉')} <b>{prompt_msg}</b>\n\n"
                                f"<i>(Reply to this message with your details so our team can activate your service!)</i>"
                            )
                            try:
                                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
                                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                                ])
                                await bot.send_message(user.telegram_id, manual_confirm_text, reply_markup=kb)
                            except Exception as e:
                                logger.error(f"Failed to send manual confirm to user {user.telegram_id}: {e}")

                            return web.json_response({"status": "manual_order_pending_details"})
                        else:
                            manual_order, m_err = await create_manual_order(
                                session,
                                user.telegram_id,
                                target_var.id,
                                target_var.price,
                                customer_input=None,
                                quantity=qty
                            )
                            qty_line = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""
                            manual_confirm_text = (
                                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYPAL PAYMENT CONFIRMED & ORDER PLACED!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{manual_order.id}\n"
                                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>{qty_line}\n"
                                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{manual_order.amount:.2f}</b>\n"
                                f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Estimated Delivery:</b> within {dispatch_time}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"Our team has received your order and is processing your activation right now! You will receive details directly in this chat shortly."
                            )
                            try:
                                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
                                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                                ])
                                await bot.send_message(user.telegram_id, manual_confirm_text, reply_markup=kb)
                            except Exception as e:
                                logger.error(f"Failed to send manual confirm to user {user.telegram_id}: {e}")

                            # Alert Admins with Fulfill Button
                            from handlers.order import _background_notify_manual
                            import asyncio
                            asyncio.create_task(_background_notify_manual(
                                bot, manual_order, prod_title, target_var.name, user, None, manual_order.amount, qty
                            ))
                            return web.json_response({"status": "placed_manual"})

            # Normal Top-Up Deposit notification to user
            deposit_msg = (
                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYPAL PAYMENT CONFIRMED & CREDITED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Added:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
                f"{ce(CustomEmojis.CARD, '💳')} <b>New Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
                f"You can now purchase any subscription instantly from the store!"
            )
            try:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Explore Store", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                ])
                await bot.send_message(user.telegram_id, deposit_msg, reply_markup=kb)
            except Exception as e:
                logger.error(f"Failed to notify user of deposit: {e}")

            # Notify Admin of Deposit
            admin_dep_alert = (
                f"{ce(CustomEmojis.FIRE, '🔔')} <b>AUTO-DEPOSIT CAPTURED VIA PAYPAL!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
                f"{ce(CustomEmojis.VERIFIED, '👤')} <b>User:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
                f"{ce(CustomEmojis.KEY, '🔢')} <b>Capture ID:</b> <code>{capture_id or 'Auto'}</code>"
            )
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_dep_alert)
                except Exception:
                    pass

            return web.json_response({"status": "credited_deposit"})

    return web.json_response({"status": f"ignored_event_{event_type}"})

async def handle_oxapay_webhook_get(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "message": "OxaPay Webhook endpoint is active and listening for POST payment events."
    })

async def handle_oxapay_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    body_bytes = await request.read()

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse OxaPay webhook JSON: {e}")
        return web.Response(status=400, text="Bad JSON")

    logger.info(f"Received OxaPay Webhook Event: {payload}")

    status = str(payload.get("status") or "").lower()
    track_id = str(payload.get("trackId") or payload.get("track_id") or "")
    order_id = str(payload.get("orderId") or payload.get("order_id") or "")
    pay_amount = payload.get("payAmount") or payload.get("amount")
    pay_currency = payload.get("payCurrency") or payload.get("currency") or "USDT"
    tx_id = payload.get("txID") or payload.get("tx_id") or ""

    if status in ("paid", "completed", "success"):
        async with AsyncSessionLocal() as session:
            deposit = None
            if track_id:
                stmt = select(Deposit).where(Deposit.gateway_order_id == track_id)
                res = await session.execute(stmt)
                deposit = res.scalar_one_or_none()

            if not deposit and order_id:
                try:
                    dep_id = int(str(order_id).replace("DEP_", "").replace("BUY_", "").split("_")[0])
                    stmt = select(Deposit).where(Deposit.id == dep_id, Deposit.status == "PENDING")
                    res = await session.execute(stmt)
                    deposit = res.scalar_one_or_none()
                except Exception:
                    pass

            if not deposit:
                logger.info(f"OxaPay webhook: No matching pending deposit found for track_id={track_id}, order_id={order_id}")
                return web.Response(text="ok")

            if deposit.status in ("APPROVED", "SUCCESS"):
                logger.info(f"Deposit #{deposit.id} already approved. Skipping duplicate OxaPay webhook.")
                return web.Response(text="ok")

            # Verify status directly with OxaPay API to prevent unauthenticated/forged requests
            from payments.manager import payment_manager
            verification = await payment_manager.oxapay.verify_payment_status(deposit.gateway_order_id or track_id)
            if not verification.get("is_paid", False):
                logger.warning(f"OxaPay webhook received for #{deposit.id}, but API verification returned not paid: {verification}")
                return web.Response(text="unverified", status=400)

            # Credit deposit
            deposit, user = await credit_user_deposit_automated(session, deposit.gateway_order_id or track_id, tx_id or f"OXA_{track_id}")
            if not deposit or not user:
                return web.Response(text="ok")

            logger.info(f"Deposit #{deposit.id} successfully credited via OxaPay webhook for User {user.telegram_id} (Amount: ₹{deposit.amount})")

            # Check if this was a Direct 1-Click Purchase
            if deposit.target_variant_id:
                target_var = await get_variant(session, deposit.target_variant_id)
                if target_var:
                    is_manual = (getattr(target_var, "fulfillment_type", "AUTOMATIC") == "MANUAL")
                    prod = await get_product(session, target_var.product_id)
                    prod_title = prod.title if prod else "Digital Item"

                    order = None
                    qty = max(1, int(round(deposit.amount / target_var.price))) if target_var.price > 0 else 1
                    if not is_manual:
                        order, err = await fulfill_order(session, user.telegram_id, target_var.id, target_var.price, quantity=qty)

                    if order and getattr(order, "delivered_content", None):
                        delivery_text = (
                            f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>CRYPTO PAYMENT CONFIRMED & ORDER DELIVERED!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b> (via Crypto / OxaPay)\n\n"
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

                        # Alert Admins (broadcast deferred to user's "I Got It!" confirmation)
                        remaining = await get_available_stock_count(session, target_var.id)
                        admin_alert = (
                            f"{ce(CustomEmojis.FIRE, '🔔')} <b>CRYPTO AUTO-DELIVERED SALE (OXAPAY)!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
                            f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
                            f"{ce(CustomEmojis.KEY, '🆔')} <b>User ID:</b> <code>{user.telegram_id}</code>\n"
                            f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {target_var.name}\n"
                            f"{ce(CustomEmojis.WALLET, '💰')} <b>Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f} ({pay_amount} {pay_currency})\n"
                            f"{ce(CustomEmojis.TROPHY, '📊')} <b>Remaining Stock:</b> {remaining} available"
                        )
                        for admin_id in config.ADMIN_IDS:
                            try:
                                await bot.send_message(admin_id, admin_alert)
                            except Exception:
                                pass

                        return web.Response(text="ok")

                    else:
                        # MANUAL FULFILLMENT -> Create manual order
                        requires_input = getattr(target_var, "requires_customer_input", True)
                        dispatch_time = getattr(target_var, "manual_dispatch_time", "1–2 Hours") or "1–2 Hours"

                        if requires_input:
                            manual_order, m_err = await create_manual_order(
                                session,
                                user.telegram_id,
                                target_var.id,
                                target_var.price,
                                customer_input="Awaiting customer details...",
                                quantity=qty
                            )
                            dp = request.app.get("dp")
                            if dp and hasattr(dp, "storage"):
                                from aiogram.fsm.context import FSMContext
                                from aiogram.fsm.storage.base import StorageKey
                                from utils.states import OrderManualStates
                                fsm_state = FSMContext(
                                    storage=dp.storage,
                                    key=StorageKey(bot_id=bot.id, chat_id=user.telegram_id, user_id=user.telegram_id)
                                )
                                await fsm_state.set_state(OrderManualStates.waiting_for_input)
                                await fsm_state.update_data(
                                    order_id=manual_order.id,
                                    variant_id=target_var.id,
                                    price=target_var.price,
                                    quantity=qty,
                                    prod_title=prod_title,
                                    var_name=target_var.name,
                                    dispatch_time=dispatch_time,
                                    is_paid=True
                                )

                            prompt_msg = getattr(target_var, "input_prompt", None) or "Please send your target Email / Account username for activation:"
                            qty_line = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""
                            manual_confirm_text = (
                                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED! (Order #{manual_order.id})</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>ACTIVATION DETAILS REQUIRED</b>\n\n"
                                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>{qty_line}\n"
                                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{manual_order.amount:.2f}</b>\n"
                                f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Delivery Time:</b> within {dispatch_time}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.SPARKLE, '👉')} <b>{prompt_msg}</b>\n\n"
                                f"<i>(Reply to this message with your details so our team can activate your service!)</i>"
                            )
                            try:
                                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
                                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                                ])
                                await bot.send_message(user.telegram_id, manual_confirm_text, reply_markup=kb)
                            except Exception as e:
                                logger.error(f"Failed to send manual confirm to user {user.telegram_id}: {e}")

                            return web.Response(text="ok")
                        else:
                            manual_order, m_err = await create_manual_order(
                                session,
                                user.telegram_id,
                                target_var.id,
                                target_var.price,
                                customer_input=None,
                                quantity=qty
                            )
                            qty_line = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""
                            manual_confirm_text = (
                                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>CRYPTO PAYMENT CONFIRMED & ORDER PLACED!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{manual_order.id}\n"
                                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>{qty_line}\n"
                                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{manual_order.amount:.2f}</b>\n"
                                f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Estimated Delivery:</b> within {dispatch_time}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"Our team has received your order and is processing your activation right now! You will receive details directly in this chat shortly."
                            )
                            try:
                                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
                                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                                ])
                                await bot.send_message(user.telegram_id, manual_confirm_text, reply_markup=kb)
                            except Exception as e:
                                logger.error(f"Failed to send manual confirm to user {user.telegram_id}: {e}")

                            # Alert Admins with Fulfill Button
                            from handlers.order import _background_notify_manual
                            import asyncio
                            asyncio.create_task(_background_notify_manual(
                                bot, manual_order, prod_title, target_var.name, user, None, manual_order.amount, qty
                            ))
                            return web.Response(text="ok")

            # Normal Top-Up Deposit notification to user
            deposit_msg = (
                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>CRYPTO PAYMENT CONFIRMED & CREDITED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Added:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
                f"{ce(CustomEmojis.CARD, '💳')} <b>New Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
                f"You can now purchase any subscription instantly from the store!"
            )
            try:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Explore Store", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
                    [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
                ])
                await bot.send_message(user.telegram_id, deposit_msg, reply_markup=kb)
            except Exception as e:
                logger.error(f"Failed to notify user of deposit: {e}")

            # Notify Admin of Deposit
            admin_dep_alert = (
                f"{ce(CustomEmojis.FIRE, '🔔')} <b>AUTO-DEPOSIT CAPTURED VIA OXAPAY (CRYPTO)!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
                f"{ce(CustomEmojis.VERIFIED, '👤')} <b>User:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
                f"{ce(CustomEmojis.KEY, '🔢')} <b>Track ID:</b> <code>{track_id}</code>\n"
                f"{ce(CustomEmojis.DIAMOND, '💎')} <b>Crypto Tx:</b> <code>{tx_id or 'Confirmed'}</code>"
            )
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_dep_alert)
                except Exception:
                    pass

            return web.Response(text="ok")

    return web.Response(text="ok")

def create_webhook_app(bot: Bot, dp=None) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/webhook/razorpay", handle_razorpay_webhook_get)
    app.router.add_post("/webhook/razorpay", handle_razorpay_webhook)
    app.router.add_get("/webhook/paypal", handle_paypal_webhook_get)
    app.router.add_post("/webhook/paypal", handle_paypal_webhook)
    app.router.add_get("/webhook/oxapay", handle_oxapay_webhook_get)
    app.router.add_post("/webhook/oxapay", handle_oxapay_webhook)
    return app
