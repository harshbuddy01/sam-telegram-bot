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
from keyboards.user_keyboards import get_deposit_preset_keyboard, get_deposit_verification_keyboard, get_back_button
from payments.manager import payment_manager
from utils.emojis import Emojis, UI, CustomEmojis, ce
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
        f"💰 <b>Your Current Balance:</b> <b>{config.CURRENCY_SYMBOL}{current_balance:.2f}</b>\n"
        f"⚡ <b>Payment Method:</b> Any UPI App (GPay / PhonePe / Paytm / CRED / BHIM)\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Processing:</b> Instant verification & auto-credit"
        f"</blockquote>\n\n"
        f"Select a quick top-up amount below or enter a custom amount:"
    )
    await callback.message.edit_text(text, reply_markup=get_deposit_preset_keyboard())

@router.callback_query(F.data.startswith("depamt_"))
async def cb_deposit_amount_selected(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    amt_str = callback.data.split("_")[1]

    if amt_str == "custom":
        await state.set_state(DepositStates.waiting_for_amount)
        await callback.message.edit_text(
            f"✍️ <b>ENTER CUSTOM DEPOSIT AMOUNT</b>\n"
            f"{UI.SECTION_BAR}\n\n"
            f"Please reply with the exact amount you wish to add in {config.CURRENCY_SYMBOL} (e.g. <code>150</code> or <code>750</code>):\n\n"
            f"<i>Minimum deposit amount is {config.CURRENCY_SYMBOL}10.</i>",
            reply_markup=get_back_button("nav_deposit")
        )
        return

    amount = float(amt_str)
    await initiate_deposit_payment(callback.message, callback.from_user, amount, session, state)

@router.message(DepositStates.waiting_for_amount)
async def msg_custom_deposit_amount(message: types.Message, state: FSMContext, session: AsyncSession):
    clean_text = message.text.strip().replace(config.CURRENCY_SYMBOL, "")
    try:
        amount = float(clean_text)
        if amount < 10:
            await message.answer("⚠️ Minimum deposit amount is ₹10. Please enter a valid amount:")
            return
        if amount > 50000:
            await message.answer("⚠️ Maximum single deposit amount is ₹50,000. Please enter a valid amount:")
            return
    except ValueError:
        await message.answer("⚠️ Invalid number. Please reply with digits only (e.g. <code>150</code>):")
        return

    await state.clear()
    await initiate_deposit_payment(message, message.from_user, amount, session, state)

async def initiate_deposit_payment(
    message: types.Message,
    from_user: types.User,
    amount: float,
    session: AsyncSession,
    state: FSMContext
):
    user_id = from_user.id
    customer_name = from_user.full_name or from_user.first_name
    order_ref = f"DEP{user_id}_{int(amount)}_{int(from_user.id % 10000)}"

    # Check if Automated Gateway (Razorpay or Cashfree) is active
    active_gateway = payment_manager.default_gateway

    if active_gateway in ("RAZORPAY", "CASHFREE"):
        res = await payment_manager.create_deposit_session(
            gateway_name=active_gateway,
            user_id=user_id,
            amount=amount,
            order_id=order_ref,
            customer_name=customer_name
        )

        if res.get("success") and res.get("payment_url"):
            gateway_order_id = res.get("gateway_order_id") or res.get("order_id")
            deposit = await create_deposit_gateway(
                session=session,
                user_id=user_id,
                amount=amount,
                gateway=active_gateway,
                gateway_order_id=gateway_order_id
            )

            text = (
                f"{ce(CustomEmojis.WALLET, '💳')} <b>AUTOMATED INSTANT DEPOSIT #{deposit.id}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{ce(CustomEmojis.SPARKLE, '💰')} <b>Amount to Add:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
                f"⚡ <b>Gateway:</b> {active_gateway} (Instant Auto-Credit)\n"
                f"📱 <b>Supported:</b> Google Pay, PhonePe, Paytm, UPI, Cards, Netbanking\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👇 <i>Click the button below to pay securely:</i>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"PAY {config.CURRENCY_SYMBOL}{amount:.0f} VIA UPI / GPAY / PHONEPE", url=res["payment_url"], icon_custom_emoji_id=CustomEmojis.FIRE)],
                [InlineKeyboardButton(text="I Have Paid (Verify & Credit)", callback_data=f"chkdep_{deposit.id}", icon_custom_emoji_id=CustomEmojis.CHECK)],
                [InlineKeyboardButton(text="Cancel & Return", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
            ])
            await message.answer(text, reply_markup=kb)
            return

    # Fallback to Direct UPI QR Code Flow
    deposit = await create_deposit(session, user_id=user_id, amount=amount)
    qr_buffer = generate_upi_qr(amount=amount, note=f"Deposit_{deposit.id}")
    input_file = BufferedInputFile(qr_buffer.read(), filename=f"upi_qr_{deposit.id}.png")

    caption = (
        f"💳 <b>UPI PAYMENT INVOICE #{deposit.id}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"💰 <b>Amount to Pay:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
        f"📱 <b>UPI ID:</b> <code>{config.UPI_ID}</code>\n"
        f"👤 <b>Payee Name:</b> <code>{config.UPI_NAME}</code>"
        f"</blockquote>\n\n"
        f"<b>Payment Steps:</b>\n"
        f"1. Scan the QR code above on any UPI app (GPay/PhonePe/Paytm).\n"
        f"2. Pay exactly <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>.\n"
        f"3. Click <b>'Submit UTR / Screenshot'</b> below and upload your proof.\n\n"
        f"⚡ <i>Your wallet balance will be credited instantly once confirmed!</i>"
    )

    await message.answer_photo(
        photo=input_file,
        caption=caption,
        reply_markup=get_deposit_verification_keyboard(deposit.id)
    )

@router.callback_query(F.data.startswith("chkdep_"))
async def cb_check_automated_deposit(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer("Checking payment status with gateway...", show_alert=False)
    deposit_id = int(callback.data.split("_")[1])
    deposit = await get_deposit(session, deposit_id)

    if not deposit:
        await callback.message.answer("Deposit invoice not found.")
        return

    if deposit.status in ("APPROVED", "SUCCESS"):
        await callback.message.answer("✅ This deposit is already verified and credited to your wallet balance!")
        return

    # Check status via Gateway
    if deposit.gateway == "RAZORPAY" and deposit.gateway_order_id:
        from payments.manager import payment_manager
        status_res = await payment_manager.razorpay.verify_payment_status(deposit.gateway_order_id)
        if status_res.get("is_paid"):
            dep, user = await credit_user_deposit_automated(session, deposit.gateway_order_id)
            text = (
                f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & CREDITED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
                f"💰 <b>Amount Added:</b> <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
                f"💳 <b>New Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
                f"You can now purchase any subscription instantly from the store!"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛍️ Explore Store", callback_data="nav_shop")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
            ])
            await callback.message.edit_text(text, reply_markup=kb)
            return

    await callback.message.answer(
        "⏳ <b>Payment Not Detected Yet</b>\n\n"
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
        f"📸 <b>SUBMIT PAYMENT PROOF FOR DEPOSIT #{deposit_id}</b>\n"
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
        await message.answer("⚠️ Please send either text (UTR number) or a screenshot image.")
        return

    deposit = await update_deposit_proof(
        session=session,
        deposit_id=deposit_id,
        utr_number=utr_number,
        proof_file_id=proof_file_id
    )

    if not deposit:
        await message.answer("⚠️ Deposit record not found. Please try again.")
        return

    confirm_text = (
        f"✅ <b>PAYMENT PROOF SUBMITTED SUCCESSFULLY!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
        f"💰 <b>Amount:</b> {config.CURRENCY_SYMBOL}{deposit.amount:.2f}\n"
        f"🔢 <b>Submitted UTR:</b> <code>{utr_number or 'Screenshot Provided'}</code>"
        f"</blockquote>\n\n"
        f"⏳ Our admin team is reviewing your transaction. Your wallet will be credited within <b>2-5 minutes</b>.\n\n"
        f"<i>You will receive a notification as soon as it is approved!</i>"
    )
    await message.answer(confirm_text, reply_markup=get_back_button("nav_home"))

    # Send Notification to Admins
    admin_alert_text = (
        f"🔔 <b>NEW DEPOSIT PENDING APPROVAL!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
        f"👤 <b>User:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"🆔 <b>Telegram ID:</b> <code>{message.from_user.id}</code>\n"
        f"💰 <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
        f"🔢 <b>UTR / Note:</b> <code>{utr_number or 'See Attached Photo'}</code>"
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
