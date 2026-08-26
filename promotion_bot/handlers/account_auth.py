from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from core.client import tg_manager
import config

router = Router(name="account_auth")

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_otp = State()
    waiting_for_2fa = State()

def get_auth_menu_keyboard(is_connected: bool) -> InlineKeyboardMarkup:
    kb = []
    if not is_connected:
        kb.append([InlineKeyboardButton(text="🔑 Login with Phone & OTP", callback_data="auth_start_login")])
    else:
        kb.append([InlineKeyboardButton(text="📋 View String Session (for Railway)", callback_data="auth_view_session")])
        kb.append([InlineKeyboardButton(text="🔄 Test Connection", callback_data="auth_test_conn")])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "menu_auth")
async def cb_auth_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()

    is_auth = tg_manager.is_connected
    status_text = "❌ <b>Not Connected</b>"
    user_details = "<i>Please login below so the bot can broadcast messages to groups using your Telegram account / Premium emojis.</i>"

    if is_auth:
        me = await tg_manager.get_me()
        if me:
            premium = "👑 Premium Active" if getattr(me, 'premium', False) else "Standard Account"
            status_text = "🟢 <b>Connected & Ready</b>"
            user_details = (
                f"• <b>Account:</b> @{me.username or me.first_name}\n"
                f"• <b>User ID:</b> <code>{me.id}</code>\n"
                f"• <b>Status:</b> <code>{premium}</code>\n"
                f"• <b>Phone:</b> <code>+{getattr(me, 'phone', 'N/A')}</code>"
            )

    text = (
        "📱 <b>TELEGRAM SENDER ACCOUNT SETUP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Status:</b> {status_text}\n\n"
        f"{user_details}\n\n"
        "💡 <i>This account will join your groups and broadcast messages with custom Telegram Premium emojis.</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_auth_menu_keyboard(is_auth))
    await query.answer()

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
        "📱 <b>Enter Your Phone Number</b>\n\n"
        "Please send the phone number of the Telegram account you want to use for promotions (with international country code).\n\n"
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
            f"Telegram has sent a verification code to your official Telegram app.\n\n"
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
            "🎉 <b>LOGIN SUCCESSFUL!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Connected Account:</b> {res.get('user')}\n\n"
            "📋 <b>Your String Session (Save this for Railway):</b>\n"
            f"<code>{session_str}</code>\n\n"
            "💡 <i>Copy the string above and set <code>SESSION_STRING</code> in Railway environment variables for persistent cloud deployment!</i>"
        )
        await wait_msg.edit_text(success_text, parse_mode="HTML", reply_markup=get_auth_menu_keyboard(True))
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
            "🎉 <b>LOGIN SUCCESSFUL!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Connected Account:</b> {res.get('user')}\n\n"
            "📋 <b>Your String Session (Save this for Railway):</b>\n"
            f"<code>{session_str}</code>\n\n"
            "💡 <i>Copy the string above and set <code>SESSION_STRING</code> in Railway environment variables!</i>"
        )
        await wait_msg.edit_text(success_text, parse_mode="HTML", reply_markup=get_auth_menu_keyboard(True))
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
            f"📋 <b>Your Telethon String Session:</b>\n\n<code>{sess}</code>\n\n"
            f"<i>Set this as <code>SESSION_STRING</code> in your Railway Environment Variables.</i>",
            parse_mode="HTML"
        )
    else:
        await query.answer("No active session string found.", show_alert=True)
    await query.answer()

@router.callback_query(F.data == "auth_test_conn")
async def cb_test_conn(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    me = await tg_manager.get_me()
    if me:
        prem = "👑 Active" if getattr(me, 'premium', False) else "Standard"
        await query.answer(f"Connected as @{me.username or me.first_name} | Premium: {prem}", show_alert=True)
    else:
        await query.answer("Client not connected.", show_alert=True)
