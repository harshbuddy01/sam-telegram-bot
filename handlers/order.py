import asyncio
from typing import Optional, Dict, Any, List
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_user,
    get_variant,
    get_product,
    fulfill_order,
    create_manual_order,
    get_available_stock_count,
    create_deposit,
    create_deposit_gateway
)
from utils.states import OrderManualStates
from utils.emojis import Emojis, UI, format_emoji, CustomEmojis, ce
from utils.templates import render_template
from utils.notifications import send_order_notification
from keyboards.user_keyboards import get_post_delivery_keyboard
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config

router = Router()

async def _background_notify(bot, order, prod_title, variant, user, remaining, amount):
    """Fire-and-forget admin + group notifications."""
    admin_alert = (
        f"{ce(CustomEmojis.FIRE, '🔔')} <b>NEW AUTO-DELIVERED SALE!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {user.full_name} (@{user.username or 'NoUser'})\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>User ID:</b> <code>{user.id}</code>\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {variant.name}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Paid:</b> {config.CURRENCY_SYMBOL}{amount:.2f}\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Remaining Stock:</b> {remaining} available"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_alert)
        except Exception:
            pass
    try:
        bot_me = getattr(bot, '_cached_me', None) or await bot.me()
        await send_order_notification(
            bot=bot,
            order_id=order.id,
            buyer_name=user.full_name,
            product_title=prod_title,
            variant_name=variant.name,
            amount=amount,
            stock_left=remaining,
            bot_username=bot_me.username or ""
        )
    except Exception:
        pass

# In-memory lock to debounce multiple rapid clicks from the same user
_generating_sessions = set()

@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_variant(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    if user_id in _generating_sessions:
        await callback.answer("⏳ Generating your payment QR... Please wait a moment!", show_alert=False)
        return

    _generating_sessions.add(user_id)
    try:
        await callback.answer("⚡ Generating Secure Razorpay UPI QR... Please wait!", show_alert=False)
        variant_id = int(callback.data.split("_")[1])
        variant = await get_variant(session, variant_id)

        if not variant:
            await callback.message.answer("Selected plan was not found.")
            return

        user = await get_user(session, user_id)
        if not user:
            await callback.message.answer("User profile not found. Please type /start.")
            return

        product = await get_product(session, variant.product_id)
        prod_title = product.title if product else "Digital Item"
        prod_icon = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id) if product else "📦"

        # 1. Check Wallet Balance -> If 0/insufficient, trigger Direct 1-Click Checkout
        if user.balance < variant.price:
            from payments.manager import payment_manager
            available_gateways = payment_manager.get_available_gateways()

            # If multiple automated gateways are configured, present a clean 3-option selector
            if len(available_gateways) > 1:
                _, _, _, pp_usd = payment_manager.paypal.calculate_amounts(variant.price)
                _, _, _, oxa_usd = payment_manager.oxapay.calculate_amounts(variant.price)

                text = (
                    f"{ce(CustomEmojis.DIAMOND, '💎')} <b>SELECT PAYMENT METHOD FOR 1-CLICK ORDER</b>\n"
                    f"{UI.SECTION_BAR}\n\n"
                    f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_icon} <b>{prod_title}</b> — <b>{variant.name}</b>\n"
                    f"{ce(CustomEmojis.WALLET, '💰')} <b>Item Price:</b> <b>{config.CURRENCY_SYMBOL}{variant.price:.2f}</b>\n\n"
                    f"<i>Choose your preferred payment method for instant automated delivery:</i>\n\n"
                    f"<blockquote>"
                    f"{ce(CustomEmojis.FIRE, '⚡')} <b>Instant UPI:</b> {config.CURRENCY_SYMBOL}{variant.price:.0f} (GPay / PhonePe / Paytm / CRED)\n"
                    f"{ce(CustomEmojis.CARD, '🅿️')} <b>PayPal & Cards:</b> ${pp_usd:.2f} USD (Visa / Mastercard / Amex)\n"
                    f"{ce(CustomEmojis.STAR, '🪙')} <b>Crypto (OxaPay):</b> ${oxa_usd:.2f} USDT (USDT / BTC / SOL / TRX)"
                    f"</blockquote>"
                )
                buttons = []
                if payment_manager.razorpay.is_configured:
                    buttons.append([
                        InlineKeyboardButton(text=f"⚡ Instant UPI / Razorpay ({config.CURRENCY_SYMBOL}{variant.price:.0f})", callback_data=f"buygw_razorpay_{variant.id}")
                    ])
                if payment_manager.paypal.is_configured:
                    buttons.append([
                        InlineKeyboardButton(text=f"🅿️ PayPal & Cards (${pp_usd:.2f} USD)", callback_data=f"buygw_paypal_{variant.id}")
                    ])
                if payment_manager.oxapay.is_configured:
                    buttons.append([
                        InlineKeyboardButton(text=f"🪙 Crypto via OxaPay (${oxa_usd:.2f} USDT)", callback_data=f"buygw_oxapay_{variant.id}")
                    ])
                buttons.append([
                    InlineKeyboardButton(text="◀️ Back to Plans", callback_data=f"prod_{variant.product_id}")
                ])
                await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                return

            await initiate_1click_checkout(callback.message, user, variant, prod_title, prod_icon, session)
            return

        # 2. Check Fulfillment Mode (MANUAL vs AUTOMATIC)
        is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")

        if is_manual:
            # Prompt customer for email/details
            await state.set_state(OrderManualStates.waiting_for_input)
            await state.update_data(
                variant_id=variant.id,
                price=variant.price,
                prod_title=prod_title,
                var_name=variant.name,
                dispatch_time=getattr(variant, "manual_dispatch_time", "1–2 Hours") or "1–2 Hours"
            )

            prompt_msg = getattr(variant, "input_prompt", None) or "Please send your target Email / Account username for activation:"
            text = (
                f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>ACTIVATION DETAILS REQUIRED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_icon} {prod_title}\n"
                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Price:</b> <b>{config.CURRENCY_SYMBOL}{variant.price:.2f}</b>\n"
                f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Dispatch Time:</b> within {getattr(variant, 'manual_dispatch_time', '1–2 Hours')}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{ce(CustomEmojis.SPARKLE, '👉')} <b>{prompt_msg}</b>\n\n"
                f"<i>(Reply to this message with your details to complete your order)</i>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️  Cancel & Go Back", callback_data=f"var_{variant.id}")]
            ])
            await callback.message.edit_text(text, reply_markup=kb)
            return

        # 3. AUTOMATIC Fulfillment (Draws 1 stock from inventory)
        order, error_msg = await fulfill_order(session, user.telegram_id, variant.id, variant.price)
        
        if error_msg or not order:
            await callback.message.answer(
                f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Purchase Error:</b> {error_msg or 'Unknown error occurred.'}",
                show_alert=True
            )
            return

        remaining_stock = await get_available_stock_count(session, variant.id)

        delivery_text = await render_template(
            session,
            "delivery_text",
            order_id=order.id,
            prod_title=prod_title,
            variant_name=variant.name,
            currency=config.CURRENCY_SYMBOL,
            price=f"{order.amount:.2f}",
            delivered_content=order.delivered_content,
            store_name=config.STORE_NAME
        )

        kb = get_post_delivery_keyboard(order.id)

        await callback.message.edit_text(delivery_text, reply_markup=kb)

        asyncio.create_task(_background_notify(
            bot, order, prod_title, variant, callback.from_user, remaining_stock, order.amount
        ))
    finally:
        _generating_sessions.discard(user_id)

@router.message(OrderManualStates.waiting_for_input)
async def msg_order_manual_input(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    cust_input = message.text.strip()
    data = await state.get_data()
    variant_id = data.get("variant_id")
    price = data.get("price")
    prod_title = data.get("prod_title", "Digital Item")
    var_name = data.get("var_name", "Plan")
    dispatch_time = data.get("dispatch_time", "1–2 Hours")

    if not variant_id or not price:
        await state.clear()
        await message.answer("Order session expired. Please choose your item again from the store.")
        return

    user = await get_user(session, message.from_user.id)
    if not user or user.balance < price:
        await state.clear()
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Insufficient balance to place order.")
        return

    # Deduct balance & create manual order
    order, err_msg = await create_manual_order(
        session=session,
        user_id=message.from_user.id,
        variant_id=variant_id,
        amount=price,
        customer_input=cust_input
    )
    await state.clear()

    if err_msg or not order:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to place order: {err_msg}")
        return

    text = (
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>ORDER PLACED SUCCESSFULLY!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{var_name}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{price:.2f}</b>\n"
        f"{ce(CustomEmojis.VERIFIED, '📧')} <b>Provided Details:</b> <code>{cust_input}</code>\n"
        f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Delivery Time:</b> within {dispatch_time}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Our support team has received your order! Your invitation/credentials will be delivered directly here once dispatched."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛟 Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton(text="🛍️ Continue Shopping", callback_data="nav_shop")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
    ])
    await message.answer(text, reply_markup=kb)

    # Background notifications
    asyncio.create_task(_background_notify_manual(
        bot, order, prod_title, var_name, message.from_user, cust_input, price
    ))

async def _background_notify_manual(bot: Bot, order, prod_title: str, var_name: str, user_obj, cust_input: str, price: float):
    from keyboards.admin_keyboards import get_admin_order_actions_keyboard
    admin_alert = (
        f"{ce(CustomEmojis.FIRE, '🚨')} <b>NEW MANUAL ORDER REQUIRES DISPATCH!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {user_obj.full_name} (@{user_obj.username or 'NoUser'})\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Telegram ID:</b> <code>{user_obj.id}</code>\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_title}\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> {var_name}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> {config.CURRENCY_SYMBOL}{price:.2f}\n"
        f"{ce(CustomEmojis.VERIFIED, '📧')} <b>Customer Details:</b> <code>{cust_input}</code>\n\n"
        f"{ce(CustomEmojis.SPARKLE, '👉')} <i>Click 'Fulfill Order' below to send the link/details directly to customer:</i>"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_alert, reply_markup=get_admin_order_actions_keyboard(order.id))
        except Exception:
            pass

@router.callback_query(F.data.startswith("buygw_"))
async def cb_buy_variant_gateway(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split("_")
    gw_name = parts[1].upper()
    variant_id = int(parts[2])

    variant = await get_variant(session, variant_id)
    if not variant:
        await callback.answer("Product plan not found.", show_alert=True)
        return

    user = await get_user(session, callback.from_user.id)
    if not user:
        await callback.answer("User profile not found.", show_alert=True)
        return

    product = await get_product(session, variant.product_id)
    prod_title = product.title if product else "Digital Item"
    prod_icon = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id) if product else "📦"

    await callback.answer()
    await initiate_1click_checkout(callback.message, user, variant, prod_title, prod_icon, session, preferred_gateway=gw_name)

async def initiate_1click_checkout(
    message: types.Message,
    user,
    variant,
    prod_title: str,
    prod_icon: str,
    session: AsyncSession,
    preferred_gateway: Optional[str] = None
):
    import time
    import io
    import qrcode
    from payments.manager import payment_manager
    from aiogram.types import BufferedInputFile

    amount = variant.price
    customer_name = user.full_name or user.username or f"User {user.telegram_id}"
    order_ref = f"BUY{user.telegram_id}_{variant.id}_{int(time.time())}"

    active_gateway = (preferred_gateway or payment_manager.default_gateway).upper()

    # 1. OxaPay Crypto 1-Click Flow
    if active_gateway == "OXAPAY" and payment_manager.oxapay.is_configured:
        res = await payment_manager.oxapay.create_payment_order(
            user_id=user.telegram_id,
            amount=amount,
            order_id=order_ref,
            customer_name=customer_name
        )
        if res.get("success"):
            gateway_order_id = res.get("gateway_order_id")
            deposit = await create_deposit_gateway(
                session=session,
                user_id=user.telegram_id,
                amount=amount,
                gateway="OXAPAY",
                gateway_order_id=gateway_order_id,
                target_variant_id=variant.id
            )

            text = (
                f"{ce(CustomEmojis.DIAMOND, '🪙')} <b>DIRECT 1-CLICK CRYPTO CHECKOUT (OXAPAY)</b>\n"
                f"{UI.SECTION_BAR}\n\n"
                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_icon} <b>{prod_title}</b>\n"
                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n\n"
                f"<blockquote>"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Item Price:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
                f"{ce(CustomEmojis.STAR, '💎')} <b>Total Amount:</b> <b>${res.get('amount_usd', 0):.2f} {res.get('currency', 'USDT')}</b>\n"
                f"{ce(CustomEmojis.FIRE, '🪙')} <b>Supported:</b> USDT (TRC20/BEP20/Polygon), BTC, ETH, SOL, TRX\n"
                f"{ce(CustomEmojis.CHECK, '🛡️')} <b>Delivery:</b> Instant Automated Delivery upon payment"
                f"</blockquote>\n\n"
                f"<i>Tap the button below to pay securely with your preferred crypto:</i>"
            )
            pay_btn_url = res.get("payment_url") or "https://oxapay.com"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🪙 PAY ${res.get('amount_usd', 0):.2f} {res.get('currency', 'USDT')} VIA OXAPAY", url=pay_btn_url)],
                [InlineKeyboardButton(text="✅ I Have Paid (Auto-Verify & Deliver)", callback_data=f"chkdep_{deposit.id}")],
                [InlineKeyboardButton(text="◀️ Cancel & Return", callback_data=f"var_{variant.id}")]
            ])
            try:
                await message.edit_text(text, reply_markup=kb)
            except Exception:
                await message.answer(text, reply_markup=kb)
            return
        else:
            err_msg = res.get("error", "OxaPay session failed.")
            await message.answer(
                f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Crypto Gateway Error:</b>\n{err_msg}\n\nPlease try again or select another payment method.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Back to Plans", callback_data=f"prod_{variant.product_id}")]
                ])
            )
            return

    # 2. PayPal 1-Click Flow
    elif active_gateway == "PAYPAL" and payment_manager.paypal.is_configured:
        res = await payment_manager.paypal.create_payment_order(
            user_id=user.telegram_id,
            amount=amount,
            order_id=order_ref,
            customer_name=customer_name
        )
        if res.get("success"):
            gateway_order_id = res.get("gateway_order_id")
            deposit = await create_deposit_gateway(
                session=session,
                user_id=user.telegram_id,
                amount=amount,
                gateway="PAYPAL",
                gateway_order_id=gateway_order_id,
                target_variant_id=variant.id
            )

            text = (
                f"{ce(CustomEmojis.DIAMOND, '🅿️')} <b>DIRECT 1-CLICK CHECKOUT (PAYPAL)</b>\n"
                f"{UI.SECTION_BAR}\n\n"
                f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_icon} <b>{prod_title}</b>\n"
                f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n\n"
                f"<blockquote>"
                f"{ce(CustomEmojis.WALLET, '💰')} <b>Item Price:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
                f"{ce(CustomEmojis.CARD, '💵')} <b>Total Amount:</b> <b>${res.get('total_usd', 0):.2f} USD</b>\n"
                f"{ce(CustomEmojis.CHECK, '🛡️')} <b>Payment Method:</b> PayPal / Debit / Credit Cards\n"
                f"{ce(CustomEmojis.FIRE, '⚡')} <b>Delivery:</b> Instant Automated Delivery upon payment"
                f"</blockquote>\n\n"
                f"<i>Tap the button below to pay securely with PayPal / Debit / Credit Card:</i>"
            )
            pay_btn_url = res.get("payment_url") or "https://paypal.com"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🅿️ PAY ${res.get('total_usd', 0):.2f} VIA PAYPAL", url=pay_btn_url)],
                [InlineKeyboardButton(text="✅ I Have Paid (Auto-Verify & Deliver)", callback_data=f"chkdep_{deposit.id}")],
                [InlineKeyboardButton(text="◀️ Cancel & Return", callback_data=f"var_{variant.id}")]
            ])
            try:
                await message.edit_text(text, reply_markup=kb)
            except Exception:
                await message.answer(text, reply_markup=kb)
            return
        else:
            err_msg = res.get("error", "PayPal session failed.")
            await message.answer(
                f"{ce(CustomEmojis.LOCK, '⚠️')} <b>PayPal Error:</b>\n{err_msg}\n\nPlease try again or select another payment method.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Back to Plans", callback_data=f"prod_{variant.product_id}")]
                ])
            )
            return

    # 3. Razorpay / Cashfree 1-Click Flow
    elif active_gateway in ("RAZORPAY", "CASHFREE") or payment_manager.razorpay.is_configured:
        res = await payment_manager.razorpay.create_qr_code(
            user_id=user.telegram_id,
            amount=amount,
            order_id=order_ref,
            customer_name=customer_name
        )
        if not res.get("success"):
            res = await payment_manager.create_deposit_session(
                gateway_name="RAZORPAY",
                user_id=user.telegram_id,
                amount=amount,
                order_id=order_ref,
                customer_name=customer_name
            )

        if res.get("success"):
            gateway_order_id = res.get("gateway_order_id") or res.get("order_id")
            deposit = await create_deposit_gateway(
                session=session,
                user_id=user.telegram_id,
                amount=amount,
                gateway="RAZORPAY",
                gateway_order_id=gateway_order_id,
                target_variant_id=variant.id
            )

            if res.get("qr_image_bytes"):
                qr_io = io.BytesIO(res["qr_image_bytes"])
                input_file = BufferedInputFile(qr_io.read(), filename=f"rzp_qr_{deposit.id}.png")
            else:
                qr_img = qrcode.make(res["payment_url"])
                qr_buf = io.BytesIO()
                qr_img.save(qr_buf, format='PNG')
                qr_buf.seek(0)
                input_file = BufferedInputFile(qr_buf.read(), filename=f"rzp_checkout_{deposit.id}.png")

            caption = await render_template(
                session,
                "checkout_text",
                prod_title=prod_title,
                prod_icon=prod_icon,
                variant_name=variant.name,
                currency=config.CURRENCY_SYMBOL,
                price=f"{amount:.2f}"
            )
            pay_btn_url = res.get("payment_url") or "https://rzp.io"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"💳 PAY {config.CURRENCY_SYMBOL}{amount:.0f} VIA RAZORPAY / UPI", url=pay_btn_url)],
                [InlineKeyboardButton(text="✅ I Have Paid (Auto-Verify & Deliver)", callback_data=f"chkdep_{deposit.id}")],
                [InlineKeyboardButton(text="Cancel & Return", callback_data=f"var_{variant.id}")]
            ])
            await message.answer_photo(photo=input_file, caption=caption, reply_markup=kb)
            return
        else:
            err_msg = res.get("error", "Payment gateway session failed.")
            await message.answer(
                f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Payment Gateway Error:</b>\n{err_msg}\n\nPlease try again shortly or contact support.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Back to Plans", callback_data=f"prod_{variant.product_id}")]
                ])
            )
            return

    # 4. Fallback if no gateway is configured
    await message.answer(
        f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Payment Gateway Offline:</b>\nNo automated payment gateway is currently active. Please contact support @{config.SUPPORT_USERNAME.lstrip('@')}.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Back to Plans", callback_data=f"prod_{variant.product_id}")]
        ])
    )
