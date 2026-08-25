from typing import Optional, Dict, Any, List
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_user,
    create_deposit,
    get_deposit,
    update_deposit_proof,
    create_deposit_gateway,
    credit_user_deposit_automated
)
from utils.qr_generator import generate_upi_qr
from utils.states import DepositStates
from keyboards.user_keyboards import get_deposit_preset_keyboard, get_deposit_verification_keyboard, get_back_button, get_post_delivery_keyboard
from payments.manager import payment_manager
from utils.emojis import Emojis, UI, CustomEmojis, ce
from utils.notifications import send_order_notification
import config

router = Router()

@router.callback_query(F.data == "nav_deposit")
async def cb_deposit_menu(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    await callback.answer()
    user = await get_user(session, callback.from_user.id)
    current_balance = user.balance if user else 0.0

    text = (
        f"{ce(CustomEmojis.WALLET, '💳')} <b>DEPOSIT / WALLET TOP-UP</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Your Current Balance:</b> <b>{config.CURRENCY_SYMBOL}{current_balance:.2f}</b>\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Payment Method:</b> Any UPI App (GPay / PhonePe / Paytm / CRED / BHIM)\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Processing:</b> Instant verification & auto-credit"
        f"</blockquote>\n\n"
        f"<i>Select a quick top-up amount below or enter a custom amount:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_deposit_preset_keyboard())

_generating_deposits = set()

@router.callback_query(F.data.startswith("depamt_"))
async def cb_deposit_amount_selected(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    amt_str = callback.data.split("_")[1]

    if amt_str == "custom":
        await state.set_state(DepositStates.waiting_for_amount)
        await callback.message.edit_text(
            f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>ENTER CUSTOM DEPOSIT AMOUNT</b>\n"
            f"{UI.SECTION_BAR}\n\n"
            f"Please reply with the exact amount you wish to add in {config.CURRENCY_SYMBOL} (e.g. <code>150</code> or <code>750</code>):\n\n"
            f"<i>Minimum deposit amount is {config.CURRENCY_SYMBOL}10.</i>",
            reply_markup=get_back_button("nav_deposit")
        )
        return

    amount = float(amt_str)
    # Check if multiple gateways are available to give user a choice
    available_gateways = payment_manager.get_available_gateways()
    if len(available_gateways) > 1:
        await prompt_payment_gateway_choice(callback.message, amount)
    else:
        await initiate_deposit_payment(callback.message, callback.from_user, amount, session, state)

@router.callback_query(F.data.startswith("deppay_"))
async def cb_deposit_gateway_chosen(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split("_")
    gw_name = parts[1].upper()
    amount = float(parts[2])
    await callback.answer()
    await initiate_deposit_payment(callback.message, callback.from_user, amount, session, state, preferred_gateway=gw_name)

async def prompt_payment_gateway_choice(message: types.Message, amount: float):
    _, _, _, pp_usd = payment_manager.paypal.calculate_amounts(amount)
    _, _, _, oxa_usd = payment_manager.oxapay.calculate_amounts(amount)

    text = (
        f"{ce(CustomEmojis.DIAMOND, '💎')} <b>SELECT DEPOSIT PAYMENT METHOD</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Deposit Amount:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n\n"
        f"<i>Select your preferred payment method below for instant automated credit:</i>\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Instant UPI:</b> {config.CURRENCY_SYMBOL}{amount:.0f} (GPay / PhonePe / Paytm / CRED)\n"
        f"{ce(CustomEmojis.CARD, '🅿️')} <b>PayPal & Cards:</b> ${pp_usd:.2f} USD (Visa / Mastercard / Amex)\n"
        f"{ce(CustomEmojis.STAR, '🪙')} <b>Crypto (OxaPay):</b> ${oxa_usd:.2f} USDT (USDT / BTC / SOL / TRX)"
        f"</blockquote>"
    )
    buttons = []
    if payment_manager.razorpay.is_configured:
        buttons.append([
            InlineKeyboardButton(text=f"⚡ Instant UPI / Razorpay ({config.CURRENCY_SYMBOL}{amount:.0f})", callback_data=f"deppay_razorpay_{int(amount)}")
        ])
    if payment_manager.paypal.is_configured:
        buttons.append([
            InlineKeyboardButton(text=f"🅿️ PayPal & Cards (${pp_usd:.2f} USD)", callback_data=f"deppay_paypal_{int(amount)}")
        ])
    if payment_manager.oxapay.is_configured:
        buttons.append([
            InlineKeyboardButton(text=f"🪙 Crypto via OxaPay (${oxa_usd:.2f} USDT)", callback_data=f"deppay_oxapay_{int(amount)}")
        ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Back to Presets", callback_data="nav_deposit")
    ])
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.message(DepositStates.waiting_for_amount)
async def msg_custom_deposit_amount(message: types.Message, state: FSMContext, session: AsyncSession):
    clean_text = message.text.strip().replace(config.CURRENCY_SYMBOL, "")
    try:
        amount = float(clean_text)
        if amount < 10:
            await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Minimum deposit amount is ₹10. Please enter a valid amount:")
            return
        if amount > 50000:
            await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Maximum single deposit amount is ₹50,000. Please enter a valid amount:")
            return
    except ValueError:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Invalid number. Please reply with digits only (e.g. <code>150</code>):")
        return

    await state.clear()
    available_gateways = payment_manager.get_available_gateways()
    if len(available_gateways) > 1:
        sent_msg = await message.answer("Preparing payment options...")
        await prompt_payment_gateway_choice(sent_msg, amount)
    else:
        await initiate_deposit_payment(message, message.from_user, amount, session, state)

async def initiate_deposit_payment(
    message: types.Message,
    from_user: types.User,
    amount: float,
    session: AsyncSession,
    state: FSMContext,
    preferred_gateway: Optional[str] = None
):
    user_id = from_user.id
    if user_id in _generating_deposits:
        await message.answer(f"{ce(CustomEmojis.FIRE, '⏳')} A deposit invoice is already being generated for you. Please wait a second!")
        return

    _generating_deposits.add(user_id)
    try:
        import time
        import io
        import qrcode
        customer_name = from_user.full_name or from_user.first_name
        order_ref = f"DEP{user_id}_{int(amount)}_{int(time.time())}"

        active_gateway = (preferred_gateway or payment_manager.default_gateway).upper()

        # 1. OxaPay Crypto Flow
        if active_gateway == "OXAPAY" and payment_manager.oxapay.is_configured:
            res = await payment_manager.oxapay.create_payment_order(
                user_id=user_id,
                amount=amount,
                order_id=order_ref,
                customer_name=customer_name
            )
            if res.get("success"):
                gateway_order_id = res.get("gateway_order_id")
                deposit = await create_deposit_gateway(
                    session=session,
                    user_id=user_id,
                    amount=amount,
                    gateway="OXAPAY",
                    gateway_order_id=gateway_order_id
                )

                text = (
                    f"{ce(CustomEmojis.DIAMOND, '🪙')} <b>AUTOMATED CRYPTO DEPOSIT #{deposit.id} (OXAPAY)</b>\n"
                    f"{UI.SECTION_BAR}\n\n"
                    f"<blockquote>"
                    f"{ce(CustomEmojis.WALLET, '💰')} <b>Wallet Credit:</b> <b>+{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
                    f"{ce(CustomEmojis.STAR, '💎')} <b>Total Amount:</b> <b>${res.get('amount_usd', 0):.2f} {res.get('currency', 'USDT')}</b>\n"
                    f"{ce(CustomEmojis.FIRE, '🪙')} <b>Supported:</b> USDT (TRC20/BEP20/Polygon), BTC, ETH, SOL, TRX\n"
                    f"{ce(CustomEmojis.CHECK, '🛡️')} <b>Processing:</b> Instant auto-credit upon blockchain confirmation"
                    f"</blockquote>\n\n"
                    f"<i>Tap 'Pay with Crypto' below. Once sent, tap 'Auto-Verify & Credit':</i>"
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"🪙 PAY ${res.get('amount_usd', 0):.2f} {res.get('currency', 'USDT')} (OXAPAY)", url=res["payment_url"])],
                    [InlineKeyboardButton(text="✅ I Have Paid (Auto-Verify & Credit)", callback_data=f"chkdep_{deposit.id}")],
                    [InlineKeyboardButton(text="◀️ Cancel & Return", callback_data="nav_home")]
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
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
                    ])
                )
                return

        # 2. PayPal Flow
        elif active_gateway == "PAYPAL" and payment_manager.paypal.is_configured:
            res = await payment_manager.paypal.create_payment_order(
                user_id=user_id,
                amount=amount,
                order_id=order_ref,
                customer_name=customer_name
            )
            if res.get("success"):
                gateway_order_id = res.get("gateway_order_id")
                deposit = await create_deposit_gateway(
                    session=session,
                    user_id=user_id,
                    amount=amount,
                    gateway="PAYPAL",
                    gateway_order_id=gateway_order_id
                )

                text = (
                    f"{ce(CustomEmojis.DIAMOND, '🅿️')} <b>AUTOMATED INSTANT DEPOSIT #{deposit.id} (PAYPAL)</b>\n"
                    f"{UI.SECTION_BAR}\n\n"
                    f"<blockquote>"
                    f"{ce(CustomEmojis.WALLET, '💰')} <b>Wallet Top-Up:</b> <b>+{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
                    f"{ce(CustomEmojis.CARD, '💵')} <b>Total Amount:</b> <b>${res.get('total_usd', 0):.2f} USD</b>\n"
                    f"{ce(CustomEmojis.CHECK, '🛡️')} <b>Payment Method:</b> PayPal / Debit / Credit Cards\n"
                    f"{ce(CustomEmojis.FIRE, '⚡')} <b>Processing:</b> Instant auto-credit upon payment"
                    f"</blockquote>\n\n"
                    f"<i>Tap 'Pay via PayPal' below to complete payment. Once done, tap 'Auto-Verify & Credit':</i>"
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"🅿️ PAY ${res.get('total_usd', 0):.2f} VIA PAYPAL", url=res["payment_url"])],
                    [InlineKeyboardButton(text="✅ I Have Paid (Auto-Verify & Credit)", callback_data=f"chkdep_{deposit.id}")],
                    [InlineKeyboardButton(text="◀️ Cancel & Return", callback_data="nav_home")]
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
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
                    ])
                )
                return

        # 3. Razorpay / Cashfree Automated Flow
        elif active_gateway in ("RAZORPAY", "CASHFREE") or payment_manager.razorpay.is_configured:
            res = await payment_manager.razorpay.create_qr_code(
                user_id=user_id,
                amount=amount,
                order_id=order_ref,
                customer_name=customer_name
            )
            if not res.get("success"):
                res = await payment_manager.create_deposit_session(
                    gateway_name="RAZORPAY",
                    user_id=user_id,
                    amount=amount,
                    order_id=order_ref,
                    customer_name=customer_name
                )

            if res.get("success"):
                gateway_order_id = res.get("gateway_order_id") or res.get("order_id")
                deposit = await create_deposit_gateway(
                    session=session,
                    user_id=user_id,
                    amount=amount,
                    gateway="RAZORPAY",
                    gateway_order_id=gateway_order_id
                )

                if res.get("qr_image_bytes"):
                    qr_io = io.BytesIO(res["qr_image_bytes"])
                    input_file = BufferedInputFile(qr_io.read(), filename=f"rzp_qr_{deposit.id}.png")
                else:
                    qr_img = qrcode.make(res["payment_url"])
                    qr_buf = io.BytesIO()
                    qr_img.save(qr_buf, format='PNG')
                    qr_buf.seek(0)
                    input_file = BufferedInputFile(qr_buf.read(), filename=f"rzp_deposit_{deposit.id}.png")

                caption = (
                    f"{ce(CustomEmojis.WALLET, '💳')} <b>AUTOMATED INSTANT DEPOSIT #{deposit.id} (RAZORPAY)</b>\n"
                    f"{UI.SECTION_BAR}\n\n"
                    f"{ce(CustomEmojis.DIAMOND, '💰')} <b>Amount to Add:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
                    f"{ce(CustomEmojis.FIRE, '⚡')} <b>Gateway:</b> Razorpay (Instant Auto-Credit)\n"
                    f"{ce(CustomEmojis.CHECK, '📱')} <b>Supported:</b> PhonePe, Google Pay, Paytm, BHIM, CRED, Cards\n\n"
                    f"{UI.SECTION_BAR}\n"
                    f"<i>Scan the official QR code above with PhonePe/GPay OR click below to pay:</i>"
                )
                pay_btn_url = res.get("payment_url") or "https://rzp.io"
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"💳 PAY {config.CURRENCY_SYMBOL}{amount:.0f} VIA RAZORPAY / UPI", url=pay_btn_url)],
                    [InlineKeyboardButton(text="✅ I Have Paid (Auto-Verify & Credit)", callback_data=f"chkdep_{deposit.id}")],
                    [InlineKeyboardButton(text="Cancel & Return", callback_data="nav_home")]
                ])
                await message.answer_photo(photo=input_file, caption=caption, reply_markup=kb)
                return
            else:
                err_msg = res.get("error", "Payment gateway session failed.")
                await message.answer(
                    f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Payment Gateway Error:</b>\n{err_msg}\n\nPlease try again shortly or contact support.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
                    ])
                )
                return

        # 4. Fallback if offline
        await message.answer(
            f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Payment Gateway Offline:</b>\nNo automated payment gateway is currently available. Please contact support @{config.SUPPORT_USERNAME.lstrip('@')}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
            ])
        )
        return
    finally:
        _generating_deposits.discard(user_id)

@router.callback_query(F.data.startswith("chkdep_"))
async def cb_check_automated_deposit(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer("Checking payment status with gateway...", show_alert=False)
    deposit_id = int(callback.data.split("_")[1])
    deposit = await get_deposit(session, deposit_id)

    if not deposit:
        await callback.message.answer("Deposit invoice not found.")
        return

    if deposit.status in ("APPROVED", "SUCCESS"):
        user = await get_user(session, callback.from_user.id)
        if deposit.target_variant_id:
            from database.crud import get_variant, fulfill_order, create_manual_order, get_product, get_available_stock_count
            target_var = await get_variant(session, deposit.target_variant_id)
            if target_var:
                is_manual = (getattr(target_var, "fulfillment_type", "AUTOMATIC") == "MANUAL")
                prod = await get_product(session, target_var.product_id)
                prod_title = prod.title if prod else "Digital Item"

                order = None
                if not is_manual:
                    order, err = await fulfill_order(session, user.telegram_id, target_var.id, target_var.price)

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
                    await callback.message.edit_text(delivery_text, reply_markup=kb)
                    return
                else:
                    # MANUAL FULFILLMENT or STOCK EMPTY -> Create manual order
                    manual_order, m_err = await create_manual_order(session, user.telegram_id, target_var.id, target_var.price, customer_input=None)
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
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🛟 Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}")],
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
                    ])
                    await callback.message.edit_text(manual_confirm_text, reply_markup=kb)
                    return

        await callback.message.answer(f"{ce(CustomEmojis.CHECK, '✅')} This deposit is already verified and credited to your wallet balance!")
        return

    # Check status via Gateways (OxaPay, PayPal, Razorpay, Cashfree)
    status_res = {"is_paid": False}
    if deposit.gateway == "OXAPAY" and deposit.gateway_order_id:
        status_res = await payment_manager.oxapay.verify_payment_status(deposit.gateway_order_id)
    elif deposit.gateway == "PAYPAL" and deposit.gateway_order_id:
        status_res = await payment_manager.paypal.verify_payment_status(deposit.gateway_order_id)
    elif deposit.gateway == "RAZORPAY" and deposit.gateway_order_id:
        status_res = await payment_manager.razorpay.verify_payment_status(deposit.gateway_order_id)
    elif deposit.gateway == "CASHFREE" and deposit.gateway_order_id:
        status_res = await payment_manager.cashfree.verify_payment_status(deposit.gateway_order_id)

    if status_res.get("is_paid"):
        dep, user = await credit_user_deposit_automated(session, deposit.gateway_order_id, status_res.get("capture_id", "AUTO_VERIFIED"))
        
        # Check if this was a Direct 1-Click Purchase
        if deposit.target_variant_id:
            from database.crud import get_variant, fulfill_order, create_manual_order, get_product, get_available_stock_count
            target_var = await get_variant(session, deposit.target_variant_id)
            if target_var:
                is_manual = (getattr(target_var, "fulfillment_type", "AUTOMATIC") == "MANUAL")
                prod = await get_product(session, target_var.product_id)
                prod_title = prod.title if prod else "Digital Item"
                
                order = None
                if not is_manual:
                    order, err = await fulfill_order(session, user.telegram_id, target_var.id, target_var.price)
                
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
                    await callback.message.edit_text(delivery_text, reply_markup=kb)

                    # Group/Channel Notification
                    remaining = await get_available_stock_count(session, target_var.id)
                    bot_me = getattr(bot, '_cached_me', None) or await bot.me()
                    await send_order_notification(
                        bot=bot,
                        order_id=order.id,
                        buyer_name=callback.from_user.full_name,
                        product_title=prod_title,
                        variant_name=target_var.name,
                        amount=order.amount,
                        stock_left=remaining,
                        bot_username=bot_me.username or ""
                    )
                    return
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
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🛟 Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}")],
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
                    ])
                    await callback.message.edit_text(manual_confirm_text, reply_markup=kb)

                    # Group/Channel Notification
                    remaining = await get_available_stock_count(session, target_var.id)
                    bot_me = getattr(bot, '_cached_me', None) or await bot.me()
                    await send_order_notification(
                        bot=bot,
                        order_id=manual_order.id,
                        buyer_name=callback.from_user.full_name,
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
                    return

        text = (
            f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & CREDITED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Added:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
            f"{ce(CustomEmojis.CARD, '💳')} <b>New Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
            f"You can now purchase any subscription instantly from the store!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Explore Store", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        return

    await callback.message.answer(
        f"{ce(CustomEmojis.FIRE, '⏳')} <b>Payment Not Detected Yet</b>\n\n"
        "If you have already paid, please wait a few seconds and tap 'Verify & Credit' again.",
        show_alert=True
    )

@router.callback_query(F.data.startswith("submitproof_"))
async def cb_submit_proof(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    deposit_id = int(callback.data.split("_")[1])
    await state.update_data(deposit_id=deposit_id)
    await state.set_state(DepositStates.waiting_for_proof)

    text = (
        f"{ce(CustomEmojis.CARD, '📸')} <b>SUBMIT PAYMENT PROOF FOR DEPOSIT #{deposit_id}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Please send the <b>12-digit UPI UTR / Ref Number</b> as text,\n"
        f"OR send a <b>Screenshot photo</b> of the successful payment."
    )
    await callback.message.answer(text, reply_markup=get_back_button("nav_home"))

@router.message(DepositStates.waiting_for_proof)
async def msg_receive_proof(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    deposit_id = data.get("deposit_id")
    await state.clear()

    utr_number = None
    proof_file_id = None

    if message.photo:
        proof_file_id = message.photo[-1].file_id
        if message.caption:
            utr_number = message.caption.strip()
    elif message.text:
        utr_number = message.text.strip()
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Please send either text (UTR number) or a screenshot image.")
        return

    deposit = await update_deposit_proof(
        session=session,
        deposit_id=deposit_id,
        utr_number=utr_number,
        proof_file_id=proof_file_id
    )

    if not deposit:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Deposit record not found. Please try again.")
        return

    confirm_text = (
        f"{ce(CustomEmojis.CHECK, '✅')} <b>PAYMENT PROOF SUBMITTED SUCCESSFULLY!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> {config.CURRENCY_SYMBOL}{deposit.amount:.2f}\n"
        f"{ce(CustomEmojis.KEY, '🔢')} <b>Submitted UTR:</b> <code>{utr_number or 'Screenshot Provided'}</code>"
        f"</blockquote>\n\n"
        f"{ce(CustomEmojis.FIRE, '⏳')} Our admin team is reviewing your transaction. Your wallet will be credited within <b>2-5 minutes</b>.\n\n"
        f"<i>You will receive a notification as soon as it is approved!</i>"
    )
    await message.answer(confirm_text, reply_markup=get_back_button("nav_home"))

    # Send Notification to Admins
    admin_alert_text = (
        f"{ce(CustomEmojis.FIRE, '🔔')} <b>NEW DEPOSIT PENDING APPROVAL!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>User:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Telegram ID:</b> <code>{message.from_user.id}</code>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
        f"{ce(CustomEmojis.KEY, '🔢')} <b>UTR / Note:</b> <code>{utr_number or 'See Attached Photo'}</code>"
    )
    from keyboards.admin_keyboards import get_deposit_approval_keyboard

    for admin_id in config.ADMIN_IDS:
        try:
            if proof_file_id:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=proof_file_id,
                    caption=admin_alert_text,
                    reply_markup=get_deposit_approval_keyboard(deposit.id)
                )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_alert_text,
                    reply_markup=get_deposit_approval_keyboard(deposit.id)
                )
        except Exception:
            pass
