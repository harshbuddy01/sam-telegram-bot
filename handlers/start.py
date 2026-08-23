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
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ <i>Verified Digital Subscriptions & Automated Delivery</i>\n\n"
        f"Hey <b>{first_name}</b> 👋 Welcome to our official store!\n\n"
        f"We provide genuine OTT subscriptions, AI subscriptions, VPNs, and tools at wholesale prices with <b>100% instant delivery</b>.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛍️ <b>Explore Store</b> ➜ Streaming, AI, VPNs & Utilities\n"
        f"🔍 <b>Search Item</b> ➜ Find any subscription instantly\n"
        f"💳 <b>Deposit Wallet</b> ➜ Automatic UPI QR top-up\n"
        f"📦 <b>Order History</b> ➜ Active accounts & keys\n"
        f"🎁 <b>Invite & Earn</b> ➜ Get {config.REFERRAL_BONUS_PERCENT}% commission per invite\n"
        f"🛟 <b>24/7 Support</b> ➜ Warranty replacements & help\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
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
        f"Click <b>'💳 Deposit Wallet'</b>, choose an amount, and pay via any UPI app (GPay / PhonePe / Paytm / CRED). Submit UTR or screenshot to get balance credited.\n\n"
        f"2️⃣ <b>Step 2 — Pick Your Subscription:</b>\n"
        f"Click <b>'🛍️ Explore Store'</b> or <b>'🔍 Search Product'</b> to select your service (Netflix, Prime, YouTube, ChatGPT, Canva, etc.).\n\n"
        f"3️⃣ <b>Step 3 — Inspect Specs & Buy:</b>\n"
        f"Review the full specifications, warranty duration, and rules. Click <b>'⚡ Purchase Now'</b>.\n\n"
        f"4️⃣ <b>Step 4 — Automated Instant Delivery:</b>\n"
        f"Your login credentials or license key will be delivered <b>instantly in chat</b> and permanently stored in <b>'📦 Order History'</b>!"
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

# ================= ENHANCED TELEGRAM CUSTOM EMOJI EXTRACTOR =================

def extract_custom_emoji_ids(message: types.Message) -> list[str]:
    """Extracts custom_emoji_id from entities, stickers, and replied messages."""
    ids = []
    
    # Check message entities
    for ent in (message.entities or []):
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            ids.append(str(ent.custom_emoji_id))

    # Check caption entities
    for ent in (message.caption_entities or []):
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            ids.append(str(ent.custom_emoji_id))

    # Check stickers
    if message.sticker and getattr(message.sticker, "custom_emoji_id", None):
        ids.append(str(message.sticker.custom_emoji_id))

    # Check replied message
    if message.reply_to_message:
        rep = message.reply_to_message
        for ent in (rep.entities or []):
            if ent.type == "custom_emoji" and ent.custom_emoji_id:
                ids.append(str(ent.custom_emoji_id))
        for ent in (rep.caption_entities or []):
            if ent.type == "custom_emoji" and ent.custom_emoji_id:
                ids.append(str(ent.custom_emoji_id))
        if rep.sticker and getattr(rep.sticker, "custom_emoji_id", None):
            ids.append(str(rep.sticker.custom_emoji_id))

    # Remove duplicates
    return list(dict.fromkeys(ids))

@router.message(Command("getemoji"))
async def cmd_getemoji(message: types.Message):
    if not config.is_admin(message.from_user.id):
        return

    emoji_ids = extract_custom_emoji_ids(message)

    if not emoji_ids:
        await message.answer(
            "ℹ️ <b>Custom Emoji Extractor Tool</b>\n\n"
            "<b>How to use:</b>\n"
            "1. Send your Telegram Premium animated emoji in chat, then <b>reply to it</b> with <code>/getemoji</code>.\n"
            "2. Or type <code>/getemoji</code> followed by a space and your premium emoji."
        )
        return

    result = "✨ <b>Detected Telegram Premium Custom Emoji ID(s):</b>\n\n"
    for eid in emoji_ids:
        result += (
            f"• <b>Emoji ID:</b> <code>{eid}</code>\n"
            f"  <b>Live Render:</b> <tg-emoji emoji-id=\"{eid}\">✨</tg-emoji>\n"
            f"  <b>HTML Code:</b> <code>&lt;tg-emoji emoji-id=\"{eid}\"&gt;✨&lt;/tg-emoji&gt;</code>\n\n"
        )

    result += "<i>Copy the HTML code to paste into any product title or description!</i>"
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
        "<i>Send or reply to any Premium emoji with <code>/getemoji</code> to grab its ID!</i>"
    )
    await message.answer(text)

@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()
