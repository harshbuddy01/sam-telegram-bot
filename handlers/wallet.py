from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, create_deposit, get_deposit
from utils.qr_generator import generate_upi_qr
from utils.states import DepositStates
from keyboards.user_keyboards import get_deposit_preset_keyboard, get_deposit_verification_keyboard, get_back_button
from utils.emojis import Emojis
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
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Current Balance:</b> {config.CURRENCY_SYMBOL}{current_balance:.2f}\n"
        f"📱 <b>Accepted Methods:</b> UPI (GPay, PhonePe, Paytm, BHIM, CRED)\n\n"
        f"Select a quick amount below or enter a custom amount to deposit:"
    )
    await callback.message.edit_text(text, reply_markup=get_deposit_preset_keyboard())

@router.callback_query(F.data.startswith("depamt_"))
async def cb_deposit_amount_selected(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    amt_str = callback.data.split("_")[1]

    if amt_str == "custom":
        await state.set_state(DepositStates.waiting_for_amount)
        await callback.message.edit_text(
            f"✍️ <b>Enter Custom Deposit Amount:</b>\n\n"
            f"Please reply with the exact amount you wish to add in {config.CURRENCY_SYMBOL} (e.g. <code>150</code> or <code>750</code>):\n\n"
            f"<i>Minimum deposit is {config.CURRENCY_SYMBOL}10.</i>",
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
        await message.answer("⚠️ Invalid number. Please reply with numeric digits only (e.g. <code>150</code>):")
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

    # Generate UPI QR Code image buffer
    qr_buffer = generate_upi_qr(amount=amount, note=f"Deposit_{deposit.id}")
    input_file = BufferedInputFile(qr_buffer.read(), filename=f"upi_qr_{deposit.id}.png")

    caption = (
        f"💳 <b>PAYMENT INSTRUCTIONS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Deposit Request ID:</b> #{deposit.id}\n"
        f"💰 <b>Amount to Pay:</b> <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b>\n"
        f"📱 <b>UPI ID:</b> <code>{config.UPI_ID}</code>\n"
        f"👤 <b>Account Name:</b> <code>{config.UPI_NAME}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>How to Pay:</b>\n"
        f"1. Scan the QR code above or copy our UPI ID: <code>{config.UPI_ID}</code>\n"
        f"2. Pay exactly <b>{config.CURRENCY_SYMBOL}{amount:.2f}</b> on your UPI app.\n"
        f"3. Click <b>'Submit UTR / Payment Proof'</b> below and send your 12-digit UTR number or screenshot.\n\n"
        f"<i>Your balance will be credited instantly once confirmed!</i>"
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
        f"📸 <b>SUBMIT PAYMENT PROOF FOR DEPOSIT #{deposit_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Please reply to this message with:\n\n"
        f"✦ <b>Payment Screenshot</b> (upload image)\n"
        f"   <b>OR</b>\n"
        f"✦ <b>12-digit UPI UTR / Reference ID</b> (send text)\n\n"
        f"<i>Our admin team will verify it immediately.</i>"
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

    # Highest resolution photo file_id
    photo_file_id = message.photo[-1].file_id
    deposit.proof_file_id = photo_file_id
    await session.commit()

    await message.answer(
        f"✅ <b>Payment Proof Submitted!</b>\n\n"
        f"Your deposit of <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b> (ID: #{deposit.id}) has been sent for verification.\n"
        f"You will receive a notification as soon as it is approved!",
        reply_markup=get_back_button("nav_home")
    )

    # Forward to Admins
    admin_caption = (
        f"🔔 <b>NEW DEPOSIT PENDING APPROVAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
        f"👤 <b>User:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"🆔 <b>Telegram ID:</b> <code>{message.from_user.id}</code>\n"
        f"💰 <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
        f"📸 <b>Proof:</b> Screenshot attached below"
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
        f"✅ <b>UTR #{utr} Submitted!</b>\n\n"
        f"Your deposit of <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b> (ID: #{deposit.id}) has been queued for verification.\n"
        f"You will receive a notification as soon as it is approved!",
        reply_markup=get_back_button("nav_home")
    )

    # Forward to Admins
    admin_alert = (
        f"🔔 <b>NEW DEPOSIT PENDING APPROVAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
        f"👤 <b>User:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"🆔 <b>Telegram ID:</b> <code>{message.from_user.id}</code>\n"
        f"💰 <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
        f"🔢 <b>Submitted UTR:</b> <code>{utr}</code>"
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
