from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from core.client import tg_manager
from database.database import AsyncSessionLocal
from database.crud import get_all_sender_accounts, get_active_sender_account, set_active_sender_account, delete_sender_account
import config

router = Router(name="account_auth")

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_otp = State()
    waiting_for_2fa = State()

def get_auth_menu_keyboard(accounts: list) -> InlineKeyboardMarkup:
    kb = []
    
    # List each saved account with switch button
    for acc in accounts:
        active_mark = "✅ [ACTIVE]" if acc.is_active else "⚪"
        prem_badge = "👑" if acc.is_premium else ""
        btn_text = f"{active_mark} {acc.phone} {prem_badge} (@{acc.username or acc.first_name or 'NoUser'})"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"switch_acc_{acc.id}")])
    
    kb.append([InlineKeyboardButton(text="➕ Add Another Number (New Account)", callback_data="auth_start_login")])
    if accounts:
        kb.append([InlineKeyboardButton(text="📋 Export Active String Session", callback_data="auth_view_session")])
        kb.append([InlineKeyboardButton(text="🗑️ Delete An Account", callback_data="auth_delete_menu")])
        
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query((F.data == "menu_auth") | (F.data == "sec_auth"))
async def cb_auth_menu(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    if state is not None:
        await state.clear()

    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        active_acc = await get_active_sender_account(session)

    if active_acc:
        prem = "👑 Telegram Premium" if active_acc.is_premium else "Standard Telegram"
        status_info = (
            f"🟢 <b>Active Sender:</b> <code>{active_acc.phone}</code>\n"
            f"• <b>User:</b> @{active_acc.username or active_acc.first_name or 'N/A'} (ID: {active_acc.user_id})\n"
            f"• <b>Type:</b> <code>{prem}</code>\n"
        )
    else:
        status_info = "❌ <i>No sender accounts connected yet. Please add a number below.</i>\n"

    text = (
        "📱 <b>MULTI-ACCOUNT SENDER MANAGER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{status_info}\n"
        f"📊 <b>Total Saved Accounts:</b> <code>{len(accounts)}</code>\n\n"
        "💡 <i>You can add multiple phone numbers and switch between them anytime! Tap any account below to make it active:</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_auth_menu_keyboard(accounts))
    await query.answer()

@router.callback_query(F.data.startswith("switch_acc_"))
async def cb_switch_account(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("switch_acc_", ""))

    async with AsyncSessionLocal() as session:
        target_acc = await set_active_sender_account(session, acc_id)

    if not target_acc:
        await query.answer("Account not found.", show_alert=True)
        return

    # Switch Telethon client
    switched = await tg_manager.switch_to_account(target_acc.session_string, target_acc.id, target_acc.phone)
    if switched:
        await query.answer(f"Switched active sender to {target_acc.phone}!", show_alert=True)
    else:
        await query.answer(f"Failed to connect to {target_acc.phone}. Check if session is valid.", show_alert=True)

    await cb_auth_menu(query, None)

@router.callback_query(F.data == "auth_start_login")
async def cb_start_login(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return

    if not config.API_ID or not config.API_HASH:
        text = (
            "⚠️ <b>API_ID & API_HASH Missing:</b>\n\n"
            "Please obtain your Telegram API credentials from https://my.telegram.org and add them to your <code>.env</code> file:\n"
            "<code>API_ID=your_id</code>\n"
            "<code>API_HASH=your_hash</code>\n\n"
            "Then restart the bot to continue."
        )
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu_auth")]
        ])
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb)
        await query.answer()
        return

    await state.set_state(AuthStates.waiting_for_phone)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_auth")]
    ])
    
    text = (
        "📱 <b>Add New Sender Phone Number</b>\n\n"
        "Please enter the phone number for the new Telegram sender account (including country code).\n\n"
        "<i>Example:</i> <code>+919876543210</code> or <code>+1234567890</code>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb)
    await query.answer()

@router.message(AuthStates.waiting_for_phone)
async def handle_auth_phone(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("⚠️ Please enter a valid phone number with country code, e.g. <code>+919876543210</code>", parse_mode="HTML")
        return

    wait_msg = await message.answer(f"⏳ <i>Sending login OTP request to {phone}...</i>", parse_mode="HTML")
    res = await tg_manager.send_auth_code(phone)

    if res.get("status") == "ok":
        await state.set_state(AuthStates.waiting_for_otp)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_auth")]
        ])
        await wait_msg.edit_text(
            f"📩 <b>OTP Code Sent to Telegram!</b>\n\n"
            f"Telegram has sent a verification code to your official Telegram app for {phone}.\n\n"
            f"<b>Please type the code below (e.g. <code>12345</code>):</b>",
            parse_mode="HTML",
            reply_markup=cancel_kb
        )
    else:
        await wait_msg.edit_text(f"❌ <b>Failed to request OTP:</b> {res.get('message')}\n\nCheck your API credentials and phone number.")
        await state.clear()

@router.message(AuthStates.waiting_for_otp)
async def handle_auth_otp(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    code = message.text.strip()

    wait_msg = await message.answer("⏳ <i>Signing in to Telegram...</i>", parse_mode="HTML")
    res = await tg_manager.sign_in_with_code(code)

    if res.get("status") == "ok":
        await state.clear()
        session_str = res.get("session_string", "")
        success_text = (
            "🎉 <b>ACCOUNT ADDED & CONNECTED!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Active User:</b> {res.get('user')}\n\n"
            "📋 <b>String Session:</b>\n"
            f"<code>{session_str}</code>\n\n"
            "💡 <i>This account is now saved and set as the active sender!</i>"
        )
        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)
        await wait_msg.edit_text(success_text, parse_mode="HTML", reply_markup=get_auth_menu_keyboard(accounts))
    elif res.get("status") == "2fa_required":
        await state.set_state(AuthStates.waiting_for_2fa)
        await wait_msg.edit_text("🔐 <b>2-Step Verification Active:</b>\nPlease enter your Telegram 2FA cloud password:")
    else:
        await wait_msg.edit_text(f"❌ <b>Sign In Error:</b> {res.get('message')}")
        await state.clear()

@router.message(AuthStates.waiting_for_2fa)
async def handle_auth_2fa(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    password = message.text.strip()

    wait_msg = await message.answer("⏳ <i>Verifying 2FA password...</i>", parse_mode="HTML")
    res = await tg_manager.sign_in_with_code(code="", password_2fa=password)

    if res.get("status") == "ok":
        await state.clear()
        session_str = res.get("session_string", "")
        success_text = (
            "🎉 <b>ACCOUNT ADDED & CONNECTED!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Active User:</b> {res.get('user')}\n\n"
            "📋 <b>String Session:</b>\n"
            f"<code>{session_str}</code>"
        )
        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)
        await wait_msg.edit_text(success_text, parse_mode="HTML", reply_markup=get_auth_menu_keyboard(accounts))
    else:
        await wait_msg.edit_text(f"❌ <b>2FA Verification Error:</b> {res.get('message')}")
        await state.clear()

@router.callback_query(F.data == "auth_view_session")
async def cb_view_session(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    sess = await tg_manager.export_session_string()
    if sess:
        await query.message.answer(
            f"📋 <b>Your Active Telethon String Session:</b>\n\n<code>{sess}</code>\n\n"
            f"<i>Set this as <code>SESSION_STRING</code> in Railway if deploying on cloud.</i>",
            parse_mode="HTML"
        )
    else:
        await query.answer("No active session found.", show_alert=True)
    await query.answer()

@router.callback_query(F.data == "auth_delete_menu")
async def cb_delete_menu(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)

    kb = []
    for a in accounts:
        kb.append([InlineKeyboardButton(text=f"🗑️ Delete {a.phone}", callback_data=f"del_acc_{a.id}")])
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu_auth")])

    await query.message.edit_text("🗑️ <b>Select Account to Delete:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await query.answer()

@router.callback_query(F.data.startswith("del_acc_"))
async def cb_delete_account(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("del_acc_", ""))
    async with AsyncSessionLocal() as session:
        await delete_sender_account(session, acc_id)
    await query.answer("Account deleted.", show_alert=True)
    await cb_auth_menu(query, None)
