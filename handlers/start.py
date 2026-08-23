from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_or_create_user, get_user
from keyboards.user_keyboards import get_main_menu_keyboard
from utils.emojis import Emojis, UI, format_emoji
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

    if config.BANNER_IMAGE_URL and config.BANNER_IMAGE_URL.startswith("http"):
        try:
            await message.answer_photo(
                photo=config.BANNER_IMAGE_URL,
                caption=text,
                reply_markup=get_main_menu_keyboard(is_admin=is_user_admin)
            )
            return
        except Exception:
            pass

    await message.answer(text, reply_markup=get_main_menu_keyboard(is_admin=is_user_admin))

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
        f"🛟 <b>24/7 CUSTOMER SUPPORT HELPDESK</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Need assistance with an order, warranty replacement, or deposit?\n\n"
        f"✦ <b>Official Support:</b> {config.SUPPORT_USERNAME}\n"
        f"✦ <b>Official Channel:</b> {config.CHANNEL_LINK}\n"
        f"✦ <b>Community Group:</b> {config.GROUP_LINK}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>All purchases come with a 100% money-back / replacement guarantee.</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬  Contact Support Agent", url=f"https://t.me/{config.SUPPORT_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="📢  Join Official Channel", url=config.CHANNEL_LINK)],
        [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "nav_guide")
async def cb_nav_guide(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"📖 <b>HOW TO BUY ON {config.STORE_NAME.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Step 1: Top-Up Wallet</b>\n"
        f"Tap <b>'Deposit Wallet'</b> on the main menu, choose an amount, and pay via any UPI app (GPay / PhonePe / Paytm).\n\n"
        f"<b>Step 2: Choose Subscription</b>\n"
        f"Tap <b>'Explore Store'</b> or <b>'Search Item'</b> to select your service (Netflix, Prime, YouTube, ChatGPT).\n\n"
        f"<b>Step 3: Instant Delivery</b>\n"
        f"Click <b>'Purchase Now'</b>. Your login email, password, and screen PIN will be delivered to your Telegram chat instantly!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>All orders are permanently saved in 'Order History' with replacement warranty!</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️  Explore Store Now", callback_data="nav_shop")],
        [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

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
            "1. Send your Telegram Premium animated emojis in chat, then <b>reply to it</b> with <code>/getemoji</code>.\n"
            "2. Or type <code>/getemoji</code> followed by a space and all your premium emojis."
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
