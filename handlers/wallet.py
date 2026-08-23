from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, create_deposit, get_deposit
from utils.qr_generator import generate_upi_qr
from utils.states import DepositStates
from keyboards.user_keyboards import get_deposit_preset_keyboard, get_deposit_verification_keyboard, get_back_button
from utils.emojis import Emojis, UI
import config

router = Router()

@router.callback_query(F.data == "nav_deposit")
async def cb_deposit_menu(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    await callback.answer()
    user = await get_user(session, callback.from_user.id)
    current_balance = user.balance if user else 0.0

    text = (
        f"💳 <b>DEPOSIT / WALLET TOP-UP</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"💰 <b>Your Current Balance:</b> <b>{config.CURRENCY_SYMBOL}{current_balance:.2f}</b>\n"
        f"⚡ <b>Payment Method:</b> Any UPI App (GPay / PhonePe / Paytm / CRED / BHIM)\n"
        f"🛡️ <b>Processing:</b> Instant verification & auto-credit"
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
    await initiate_deposit_payment(callback.message, callback.from_user.id, amount, session, state)

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
    await initiate_deposit_payment(message, message.from_user.id, amount, session, state)

async def initiate_deposit_payment(
    message: types.Message,
    user_id: int,
    amount: float,
    session: AsyncSession,
    state: FSMContext
):
    deposit = await create_deposit(session, user_id=user_id, amount=amount)

    # Generate UPI QR Code image
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

@router.callback_query(F.data.startswith("submitproof_"))
async def cb_submit_proof(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    deposit_id = int(callback.data.split("_")[1])
    await state.update_data(deposit_id=deposit_id)
    await state.set_state(DepositStates.waiting_for_proof)

    text = (
        f"📸 <b>SUBMIT PROOF FOR DEPOSIT #{deposit_id}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Please reply to this message with:\n\n"
        f"✦ <b>Payment Screenshot</b> (send photo)\n"
        f"   <i>OR</i>\n"
        f"✦ <b>12-Digit UPI UTR Number</b> (send text)\n\n"
        f"<i>Our automated admin system will verify it immediately.</i>"
    )
    await callback.message.answer(text, reply_markup=get_back_button("nav_deposit"))

@router.message(DepositStates.waiting_for_proof, F.photo)
async def msg_proof_photo(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    deposit_id = data.get("deposit_id")
    await state.clear()

    deposit = await get_deposit(session, deposit_id)
    if not deposit:
        await message.answer("Deposit session expired. Please create a new request.")
        return

    photo_file_id = message.photo[-1].file_id
    deposit.proof_file_id = photo_file_id
    await session.commit()

    await message.answer(
        f"✅ <b>Payment Proof Received!</b>\n\n"
        f"Deposit of <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b> (ID: #{deposit.id}) submitted.\n"
        f"You will get an alert as soon as it is approved!",
        reply_markup=get_back_button("nav_home")
    )

    # Forward to Admin
    admin_caption = (
        f"🔔 <b>NEW DEPOSIT PENDING APPROVAL</b>\n"
        f"{UI.SECTION_BAR}\n"
        f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
        f"👤 <b>User:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"🆔 <b>User ID:</b> <code>{message.from_user.id}</code>\n"
        f"💰 <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>"
    )
    from keyboards.admin_keyboards import get_deposit_approval_keyboard
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo_file_id,
                caption=admin_caption,
                reply_markup=get_deposit_approval_keyboard(deposit.id)
            )
        except Exception:
            pass

@router.message(DepositStates.waiting_for_proof, F.text)
async def msg_proof_utr_text(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    deposit_id = data.get("deposit_id")
    await state.clear()

    deposit = await get_deposit(session, deposit_id)
    if not deposit:
        await message.answer("Deposit session expired. Please create a new request.")
        return

    utr = message.text.strip()
    deposit.utr_number = utr
    await session.commit()

    await message.answer(
        f"✅ <b>UTR #{utr} Received!</b>\n\n"
        f"Deposit of <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b> (ID: #{deposit.id}) submitted.\n"
        f"You will get an alert as soon as it is approved!",
        reply_markup=get_back_button("nav_home")
    )

    # Forward to Admin
    admin_alert = (
        f"🔔 <b>NEW DEPOSIT PENDING APPROVAL</b>\n"
        f"{UI.SECTION_BAR}\n"
        f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
        f"👤 <b>User:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"🆔 <b>User ID:</b> <code>{message.from_user.id}</code>\n"
        f"💰 <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
        f"🔢 <b>UTR Number:</b> <code>{utr}</code>"
    )
    from keyboards.admin_keyboards import get_deposit_approval_keyboard
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_alert,
                reply_markup=get_deposit_approval_keyboard(deposit.id)
            )
        except Exception:
            pass
