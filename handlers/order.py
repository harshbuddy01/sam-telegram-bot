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
from utils.notifications import send_order_notification
from keyboards.user_keyboards import get_post_delivery_keyboard
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config

router = Router()

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
            import time
            amount = variant.price
            customer_name = user.full_name or user.username or f"User {user.telegram_id}"
            order_ref = f"BUY{user.telegram_id}_{variant.id}_{int(time.time())}"

            from payments.manager import payment_manager
            from utils.qr_generator import generate_upi_qr
            from aiogram.types import BufferedInputFile

            active_gateway = payment_manager.default_gateway

            # If Razorpay / Cashfree is active
            if active_gateway in ("RAZORPAY", "CASHFREE"):
                # First try Razorpay official Dynamic Native UPI QR
                res = await payment_manager.razorpay.create_qr_code(
                    user_id=user.telegram_id,
                    amount=amount,
                    order_id=order_ref,
                    customer_name=customer_name
                )
                if not res.get("success"):
                    # Fallback to payment_links if qr_codes is disabled
                    res = await payment_manager.create_deposit_session(
                        gateway_name=active_gateway,
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
                    gateway=active_gateway,
                    gateway_order_id=gateway_order_id,
                    target_variant_id=variant.id
                )

                import io
                if res.get("qr_image_bytes"):
                    qr_io = io.BytesIO(res["qr_image_bytes"])
                    input_file = BufferedInputFile(qr_io.read(), filename=f"rzp_qr_{deposit.id}.png")
                else:
                    import qrcode
                    qr_img = qrcode.make(res["payment_url"])
                    qr_buf = io.BytesIO()
                    qr_img.save(qr_buf, format='PNG')
                    qr_buf.seek(0)
                    input_file = BufferedInputFile(qr_buf.read(), filename=f"rzp_checkout_{deposit.id}.png")

                caption = (
                    f"{ce(CustomEmojis.FIRE, '⚡')} <b>DIRECT 1-CLICK INSTANT CHECKOUT (RAZORPAY)</b>\n"
                    f"{UI.SECTION_BAR}\n\n"
                    f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_icon} <b>{prod_title}</b>\n"
                    f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
                    f"{ce(CustomEmojis.WALLET, '💰')} <b>Total Amount:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
                    f"{ce(CustomEmojis.FIRE, '⚡')} <b>Delivery:</b> Instant Auto-Delivery upon payment\n\n"
                    f"<blockquote>"
                    f"{ce(CustomEmojis.CARD, '📱')} <b>Supported:</b> PhonePe, Google Pay, Paytm, BHIM, CRED, Cards"
                    f"</blockquote>\n\n"
                    f"{ce(CustomEmojis.SPARKLE, '👇')} <i>Scan QR code above with PhonePe/GPay OR click the button below to pay:</i>"
                )
                pay_btn_url = res.get("payment_url") or "https://rzp.io"
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"💳 PAY {config.CURRENCY_SYMBOL}{amount:.0f} VIA RAZORPAY / UPI", url=pay_btn_url)],
                    [InlineKeyboardButton(text="✅ I Have Paid (Auto-Verify & Deliver)", callback_data=f"chkdep_{deposit.id}")],
                    [InlineKeyboardButton(text="Cancel & Return", callback_data=f"var_{variant.id}")]
                ])
                await callback.message.answer_photo(photo=input_file, caption=caption, reply_markup=kb)
                return
            else:
                err_msg = res.get("error", "Payment gateway session failed.")
                await callback.message.answer(
                    f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Payment Gateway Error:</b>\n{err_msg}\n\nPlease try again shortly or contact support.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="◀️ Back to Plans", callback_data=f"prod_{variant.product_id}")]
                    ])
                )
                return

        # Direct Dynamic UPI QR Flow
        deposit = await create_deposit(session, user_id=user.telegram_id, amount=amount, target_variant_id=variant.id)
        qr_buffer = generate_upi_qr(amount=amount, note=f"Order_{deposit.id}")
        input_file = BufferedInputFile(qr_buffer.read(), filename=f"checkout_qr_{deposit.id}.png")

        caption = (
            f"{ce(CustomEmojis.FIRE, '⚡')} <b>DIRECT 1-CLICK INSTANT CHECKOUT</b>\n"
            f"{UI.SECTION_BAR}\n\n"
            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_icon} <b>{prod_title}</b>\n"
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>Total Amount:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
            f"{ce(CustomEmojis.CARD, '📱')} <b>UPI ID:</b> <code>{config.UPI_ID}</code>\n\n"
            f"<blockquote>"
            f"{ce(CustomEmojis.SPARKLE, '💻')} <b>Desktop / Web:</b> Scan QR code with your phone camera\n"
            f"{ce(CustomEmojis.CARD, '📱')} <b>Mobile:</b> Pay {config.CURRENCY_SYMBOL}{amount:.0f} via any UPI app"
            f"</blockquote>\n\n"
            f"{ce(CustomEmojis.FIRE, '⚡')} <i>Your credentials will be delivered to this chat automatically once paid!</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Submit UTR / Screenshot", callback_data=f"submitproof_{deposit.id}", icon_custom_emoji_id=CustomEmojis.CHECK)],
            [InlineKeyboardButton(text="Cancel", callback_data=f"var_{variant.id}", icon_custom_emoji_id=CustomEmojis.CROWN)]
        ])
        await callback.message.answer_photo(photo=input_file, caption=caption, reply_markup=kb)
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

        delivery_text = (
            f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>ORDER #{order.id} COMPLETED & DELIVERED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_icon} {prod_title}\n"
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
            f"{ce(CustomEmojis.CARD, '💳')} <b>Remaining Balance:</b> {config.CURRENCY_SYMBOL}{user.balance - order.amount:.2f}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{ce(CustomEmojis.KEY, '🔑')} <b>YOUR DELIVERED ACCOUNT / CODE:</b>\n"
            f"<i>(Tap the box below to copy automatically)</i>\n\n"
            f"<pre><code>{order.delivered_content}</code></pre>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Warranty Guidelines:</b>\n"
            f"✦ Do not edit account master email or passwords.\n"
            f"✦ Saved permanently in <b>Order History</b>.\n"
            f"✦ For replacement support, contact {config.SUPPORT_USERNAME}\n\n"
            f"{ce(CustomEmojis.HEART, '❤️')} <i>Thank you for shopping with {config.STORE_NAME}!</i>"
        )

        kb = get_post_delivery_keyboard(order.id)

        await callback.message.edit_text(delivery_text, reply_markup=kb)

        # Admin Alert for Instant Sale
        admin_alert = (
            f"{ce(CustomEmojis.FIRE, '🔔')} <b>NEW AUTO-DELIVERED SALE!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{order.id}\n"
            f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {callback.from_user.full_name} (@{callback.from_user.username or 'NoUser'})\n"
            f"{ce(CustomEmojis.KEY, '🆔')} <b>User ID:</b> <code>{callback.from_user.id}</code>\n"
            f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {variant.name}\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
            f"{ce(CustomEmojis.TROPHY, '📊')} <b>Remaining Stock:</b> {remaining_stock} available"
        )
        for admin_id in config.ADMIN_IDS:
            try:
                await bot.send_message(admin_id, admin_alert)
            except Exception:
                pass

        # Group/Channel Notification
        bot_me = await bot.me()
        await send_order_notification(
            bot=bot,
            order_id=order.id,
            buyer_name=callback.from_user.full_name,
            product_title=prod_title,
            variant_name=variant.name,
            amount=order.amount,
            stock_left=remaining_stock,
            bot_username=bot_me.username or ""
        )
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
    await state.clear()

    order, error_msg = await create_manual_order(
        session=session,
        user_id=message.from_user.id,
        variant_id=variant_id,
        amount=price,
        customer_input=cust_input
    )

    if error_msg or not order:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Order Error:</b> {error_msg or 'Could not place order.'}")
        return

    # Customer Confirmation Receipt
    user = await get_user(session, message.from_user.id)
    receipt_text = (
        f"{ce(CustomEmojis.SPARKLE, '⏳')} <b>ORDER #{order.id} RECEIVED — MANUAL ACTIVATION</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_title}\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <code>{var_name}</code>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
        f"{ce(CustomEmojis.VERIFIED, '📧')} <b>Target Details:</b> <code>{order.customer_input}</code>\n"
        f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Expected Dispatch:</b> Within {dispatch_time}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.SPARKLE, '💡')} <i>Our administration is processing your activation. You will receive an instant Telegram notification with your login/invite link as soon as it is dispatched!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 View Order Status", callback_data=f"orderdetail_{order.id}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
    ])
    await message.answer(receipt_text, reply_markup=kb)

    # Admin High-Priority Alert with 1-Click Fulfill & Refund Buttons
    admin_text = (
        f"{ce(CustomEmojis.FIRE, '🚨')} <b>NEW MANUAL ORDER #{order.id} REQUIRING DISPATCH!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>User ID:</b> <code>{message.from_user.id}</code>\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {var_name}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
        f"{ce(CustomEmojis.VERIFIED, '📧')} <b>Customer Input:</b> <code>{order.customer_input}</code>\n"
        f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Expected Within:</b> {dispatch_time}\n\n"
        f"<i>Click below to fulfill and deliver the credentials or refund:</i>"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Fulfill & Send Credentials", callback_data=f"adm_man_ful_{order.id}")],
        [InlineKeyboardButton(text="❌ Cancel & Refund Wallet", callback_data=f"adm_man_ref_{order.id}")]
    ])
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=admin_kb)
        except Exception:
            pass
