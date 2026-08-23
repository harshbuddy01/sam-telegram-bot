from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_or_create_user, get_user
from keyboards.user_keyboards import get_main_menu_keyboard
from utils.emojis import Emojis
import config

router = Router()

def get_welcome_text(first_name: str) -> str:
    return (
        f"👑 <b>Welcome to {config.UPI_NAME}!</b>\n\n"
        f"Hey <b>{first_name}</b> 👋\n\n"
        f"We offer premium digital subscriptions & services at the best prices. "
        f"Fast, secure, and 100% automated delivery directly inside Telegram!\n\n"
        f"<blockquote>"
        f"🛍️ <b>Shop</b> — Browse & buy subscriptions\n"
        f"💳 <b>Deposit</b> — Add funds to your wallet\n"
        f"👤 <b>My Profile</b> — Balance, orders & referral link\n"
        f"🛟 <b>Support</b> — Get instant 24/7 assistance\n"
        f"🎁 <b>Refer & Earn</b> — Invite friends and get {config.REFERRAL_BONUS_PERCENT}% commission"
        f"</blockquote>\n\n"
        f"👇 <i>Choose an option below to continue:</i>"
    )

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, session: AsyncSession):
    # Check if referral code was passed: /start ref_12345
    referrer_id = None
    if command.args and command.args.startswith("ref_"):
        ref_str = command.args.replace("ref_", "")
        if ref_str.isdigit():
            referrer_id = int(ref_str)

    user, is_new = await get_or_create_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name or message.from_user.first_name,
        referrer_id=referrer_id
    )

    is_user_admin = config.is_admin(message.from_user.id)
    text = get_welcome_text(message.from_user.first_name)
    await message.answer(
        text,
        reply_markup=get_main_menu_keyboard(is_admin=is_user_admin)
    )

@router.callback_query(F.data == "nav_home")
async def cb_nav_home(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    is_user_admin = config.is_admin(callback.from_user.id)
    text = get_welcome_text(callback.from_user.first_name)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_main_menu_keyboard(is_admin=is_user_admin)
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=get_main_menu_keyboard(is_admin=is_user_admin)
        )

@router.callback_query(F.data == "nav_support")
async def cb_nav_support(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"🛟 <b>Customer Support & Helpdesk</b>\n\n"
        f"Have a question or facing issues with an order?\n"
        f"Our support team is available to assist you.\n\n"
        f"✦ <b>Official Support:</b> {config.SUPPORT_USERNAME}\n"
        f"✦ <b>Working Hours:</b> 24/7 Online Support\n"
        f"✦ <b>Updates Channel:</b> <a href='{config.CHANNEL_LINK}'>Join Channel</a>\n\n"
        f"<i>Click the button below to reach out to our team directly.</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Contact Support", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}")] if config.SUPPORT_USERNAME.startswith('@') else [],
        [InlineKeyboardButton(text=f"{Emojis.BACK} Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)

@router.message(Command("getemoji"))
async def cmd_getemoji(message: types.Message):
    """
    Admin helper command to extract custom_emoji_id from Telegram Premium custom emojis.
    Usage: Send /getemoji followed by the custom emoji or reply to any message containing a premium emoji.
    """
    if not config.is_admin(message.from_user.id):
        return

    emoji_ids = []
    # Check entities in current message
    entities = message.entities or []
    for ent in entities:
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            emoji_ids.append(ent.custom_emoji_id)

    # Check replied message
    if message.reply_to_message and message.reply_to_message.entities:
        for ent in message.reply_to_message.entities:
            if ent.type == "custom_emoji" and ent.custom_emoji_id:
                emoji_ids.append(ent.custom_emoji_id)

    if not emoji_ids:
        await message.answer(
            "ℹ️ <b>Custom Emoji Extractor</b>\n\n"
            "Send or reply to a message containing a <b>Telegram Premium Custom Emoji</b> with <code>/getemoji</code> to get its ID."
        )
        return

    result = "✨ <b>Found Custom Emoji ID(s):</b>\n\n"
    for eid in emoji_ids:
        result += f"• <code>{eid}</code>\n"
        result += f"  HTML Tag: <code>&lt;tg-emoji emoji-id=\"{eid}\"&gt;🔥&lt;/tg-emoji&gt;</code>\n\n"

    await message.answer(result)

@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()
