from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_or_create_user, get_user
from keyboards.user_keyboards import get_main_menu_keyboard
from utils.emojis import Emojis, UI
import config

router = Router()

def get_welcome_text(first_name: str) -> str:
    return (
        f"👑 <b>{config.STORE_NAME.upper()}</b>\n"
        f"<i>Premium Subscriptions & Instant Automated Delivery</i>\n\n"
        f"Hey <b>{first_name}</b> 👋\n\n"
        f"Welcome to our official store! Explore our genuine digital subscriptions, streaming accounts, AI tools, and VPNs with <b>100% instant delivery</b>.\n\n"
        f"<blockquote>"
        f"🛍️ <b>Explore Store</b> — Streaming, AI, VPNs & Services\n"
        f"💳 <b>Deposit Funds</b> — Fast UPI wallet top-up\n"
        f"👤 <b>My Account</b> — Balance, orders & live accounts\n"
        f"🎁 <b>Refer & Earn</b> — Get {config.REFERRAL_BONUS_PERCENT}% cash on every order\n"
        f"🛟 <b>24/7 Support</b> — Instant warranty & assistance"
        f"</blockquote>\n\n"
        f"👇 <i>Select an option below to get started:</i>"
    )

@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, session: AsyncSession):
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

@router.callback_query(F.data == "nav_guide")
async def cb_nav_guide(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"📖 <b>HOW TO USE {config.STORE_NAME.upper()}</b>\n\n"
        f"Follow these simple steps to buy subscriptions with instant delivery:\n\n"
        f"<blockquote>"
        f"1️⃣ <b>Step 1 — Deposit Funds:</b>\n"
        f"Click <b>'💳 Deposit Wallet'</b>, select an amount, and scan our UPI QR code. Submit your UTR/screenshot to get your balance credited in minutes.\n\n"
        f"2️⃣ <b>Step 2 — Browse Catalog or Search:</b>\n"
        f"Click <b>'🛍️ Explore Store'</b> or <b>'🔍 Search Product'</b> to find your subscription (Netflix, Prime, YouTube, VPN, etc.).\n\n"
        f"3️⃣ <b>Step 3 — Inspect Details & Purchase:</b>\n"
        f"Click on your plan to see full specifications, rules, and warranty. Click <b>'⚡ Purchase Now'</b>.\n\n"
        f"4️⃣ <b>Step 4 — Instant Delivery:</b>\n"
        f"Your login credentials or license key will be sent <b>immediately in the chat</b> and permanently saved in <b>'📦 Order History'</b>!"
        f"</blockquote>\n\n"
        f"💡 <i>Need assistance? Click 'Help & Support' below anytime.</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️  Explore Store Now", callback_data="nav_shop")],
        [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "nav_support")
async def cb_nav_support(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"🛟 <b>CUSTOMER SUPPORT & HELPDESK</b>\n\n"
        f"Need assistance with an order, replacement, or inquiry?\n"
        f"Our support desk is online 24/7 to help you.\n\n"
        f"<blockquote>"
        f"✦ <b>Official Handle:</b> {config.SUPPORT_USERNAME}\n"
        f"✦ <b>Response Time:</b> Within 5–15 Minutes\n"
        f"✦ <b>Warranty Policy:</b> 100% Replacement Guarantee\n"
        f"✦ <b>Official Channel:</b> <a href='{config.CHANNEL_LINK}'>Join Updates</a>"
        f"</blockquote>\n\n"
        f"💬 <i>Click below to message our support team directly:</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬  Message Support Directly", url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}")] if config.SUPPORT_USERNAME.startswith('@') else [],
        [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)

@router.message(Command("getemoji"))
async def cmd_getemoji(message: types.Message):
    if not config.is_admin(message.from_user.id):
        return

    emoji_ids = []
    entities = message.entities or []
    for ent in entities:
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            emoji_ids.append(ent.custom_emoji_id)

    if message.reply_to_message and message.reply_to_message.entities:
        for ent in message.reply_to_message.entities:
            if ent.type == "custom_emoji" and ent.custom_emoji_id:
                emoji_ids.append(ent.custom_emoji_id)

    if not emoji_ids:
        await message.answer(
            "ℹ️ <b>Custom Emoji Extractor Tool</b>\n\n"
            "Send or reply to a message containing a <b>Telegram Premium Custom Emoji</b> with <code>/getemoji</code> to get its ID."
        )
        return

    result = "✨ <b>Detected Telegram Premium Emoji ID(s):</b>\n\n"
    for eid in emoji_ids:
        result += f"• <b>Custom ID:</b> <code>{eid}</code>\n"
        result += f"  <b>Live Preview:</b> <tg-emoji emoji-id=\"{eid}\">✨</tg-emoji>\n"
        result += f"  <b>HTML Tag:</b> <code>&lt;tg-emoji emoji-id=\"{eid}\"&gt;✨&lt;/tg-emoji&gt;</code>\n\n"

    result += "<i>You can paste this &lt;tg-emoji&gt; tag into any product title, category name, or plan description!</i>"
    await message.answer(result)

@router.message(Command("testemoji"))
async def cmd_testemoji(message: types.Message):
    if not config.is_admin(message.from_user.id):
        return

    text = (
        "✨ <b>Telegram Custom Emoji Status Test</b>\n\n"
        "✦ <b>HTML Parse Mode:</b> Enabled ✅\n"
        "✦ <b>&lt;tg-emoji&gt; Tag Support:</b> Integrated ✅\n"
        "✦ <b>Bot Custom Emoji Capability:</b> Active ✅\n\n"
        "<i>Send any Premium emoji using <code>/getemoji &lt;emoji&gt;</code> to extract its ID for your products!</i>"
    )
    await message.answer(text)

@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()
