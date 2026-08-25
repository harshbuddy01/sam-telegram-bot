from aiogram import Router, F, types, Bot
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_or_create_user, get_user
from keyboards.user_keyboards import get_main_menu_keyboard, get_persistent_menu_keyboard
from utils.emojis import Emojis, UI, format_emoji, CustomEmojis, ce
from utils.templates import render_template
import config

router = Router()

async def get_welcome_text(first_name: str, session: AsyncSession = None) -> str:
    if session:
        return await render_template(session, "welcome_text", store_name=config.STORE_NAME, first_name=first_name)
    return (
        f"{ce(CustomEmojis.CROWN, '👑')} <b>{config.STORE_NAME.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <i>Verified Digital Subscriptions & Automated Delivery</i>\n\n"
        f"Hey <b>{first_name}</b> {ce(CustomEmojis.SPARKLE, '👋')} Welcome to our official store!\n\n"
        f"We provide genuine OTT subscriptions, AI subscriptions, VPNs, and tools at wholesale prices with <b>100% instant delivery</b>.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.SHOP, '🛍️')} <b>Explore Store</b> ➜ Streaming, AI, VPNs & Utilities\n"
        f"{ce(CustomEmojis.SEARCH, '🔍')} <b>Search Item</b> ➜ Find any subscription instantly\n"
        f"{ce(CustomEmojis.WALLET, '💳')} <b>Deposit Wallet</b> ➜ Automatic UPI QR top-up\n"
        f"{ce(CustomEmojis.ORDERS, '📦')} <b>Order History</b> ➜ Active accounts & keys\n"
        f"{ce(CustomEmojis.REFER, '🎁')} <b>Invite & Earn</b> ➜ Get {config.REFERRAL_BONUS_PERCENT}% commission per invite\n"
        f"{ce(CustomEmojis.SUPPORT, '🛟')} <b>24/7 Support</b> ➜ Warranty replacements & help\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.SPARKLE, '👇')} <b>Select an option from the menu below:</b>"
    )

@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot, session: AsyncSession, command: CommandObject = None):
    referrer_id = None
    if command and command.args:
        args = command.args.strip()
        if args.startswith("ref_"):
            try:
                referrer_id = int(args.split("_")[1])
                if referrer_id == message.from_user.id:
                    referrer_id = None
            except ValueError:
                pass

    user, is_new = await get_or_create_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name or message.from_user.first_name,
        referrer_id=referrer_id
    )

    is_user_admin = config.is_admin(message.from_user.id)
    text = await get_welcome_text(message.from_user.first_name, session)

    # Attach persistent bottom reply keyboard
    await message.answer(
        f"{ce(CustomEmojis.SPARKLE, '👋')} <i>Welcome to {config.STORE_NAME}! Use the quick menu below or tap buttons to explore:</i>",
        reply_markup=get_persistent_menu_keyboard(is_admin=is_user_admin)
    )

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
    text = await get_welcome_text(callback.from_user.first_name, session)
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
async def cb_nav_support(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    text = await render_template(
        session,
        "support_text",
        support_username=config.SUPPORT_USERNAME.replace('@', ''),
        channel_link=config.CHANNEL_LINK,
        group_link=config.GROUP_LINK
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [
        [InlineKeyboardButton(text="Contact Support Agent", url=f"https://t.me/{config.SUPPORT_USERNAME.replace('@', '')}", icon_custom_emoji_id=CustomEmojis.SUPPORT)]
    ]
    if config.CHANNEL_LINK:
        buttons.append([InlineKeyboardButton(text="Join Official Channel", url=config.CHANNEL_LINK, icon_custom_emoji_id=CustomEmojis.TELEGRAM if hasattr(CustomEmojis, 'TELEGRAM') else None)])
    buttons.append([InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "nav_guide")
async def cb_nav_guide(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        f"{ce(CustomEmojis.DIAMOND, '📖')} <b>HOW TO BUY ON {config.STORE_NAME.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Step 1: Top-Up Wallet</b>\n"
        f"Tap <b>'Deposit Wallet'</b> on the main menu, choose an amount, and pay via any UPI app (GPay / PhonePe / Paytm).\n\n"
        f"<b>Step 2: Choose Subscription</b>\n"
        f"Tap <b>'Explore Store'</b> or <b>'Search Item'</b> to select your service (Netflix, Prime, YouTube, ChatGPT).\n\n"
        f"<b>Step 3: Instant Delivery</b>\n"
        f"Click <b>'Purchase Now'</b>. Your login email, password, and screen PIN will be delivered to your Telegram chat instantly!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>All orders are permanently saved in 'Order History' with replacement warranty!</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Explore Store Now", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
        [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

# Persistent Bottom Menu Shortcuts
@router.message(F.text.in_(["🛍️  Shop", "🛍️ Shop", "Shop", "🏪 Shop"]))
async def msg_btn_shop(message: types.Message, session: AsyncSession):
    from database.crud import get_active_categories
    from keyboards.user_keyboards import get_categories_keyboard
    categories = await get_active_categories(session)
    cat_lines = []
    for cat in categories:
        if "<tg-emoji" in cat.name:
            cat_lines.append(f"• <b>{cat.name}</b>")
        else:
            icon = format_emoji(cat.emoji or "📁", cat.custom_emoji_id)
            cat_lines.append(f"• {icon} <b>{cat.name}</b>")
    cat_block = "\n".join(cat_lines) if cat_lines else "<i>No categories active yet.</i>"
    text = (
        f"{ce(CustomEmojis.SHOP, '🛍️')} <b>PREMIUM DIGITAL STORE CATALOG</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>Available Categories:</b>\n"
        f"{cat_block}\n\n"
        f"{ce(CustomEmojis.SPARKLE, '👇')} <i>Choose a category below to explore:</i>"
    )
    await message.answer(text, reply_markup=get_categories_keyboard(categories))

@router.message(F.text.in_(["💳  Deposit", "💳 Deposit", "Deposit", "💼 Deposit"]))
async def msg_btn_deposit(message: types.Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    from keyboards.user_keyboards import get_deposit_preset_keyboard
    user = await get_user(session, message.from_user.id)
    balance = user.balance if user else 0.0
    text = (
        f"{ce(CustomEmojis.WALLET, '💳')} <b>WALLET TOP-UP & INSTANT DEPOSIT</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Current Balance:</b> <code>{config.CURRENCY_SYMBOL}{balance:.2f}</code>\n\n"
        f"Choose an instant top-up preset below (Automated UPI QR):"
    )
    await message.answer(text, reply_markup=get_deposit_preset_keyboard())

@router.message(F.text.in_(["👤  My Profile", "👤 My Profile", "My Profile", "Profile"]))
async def msg_btn_profile(message: types.Message, session: AsyncSession):
    from database.crud import get_user_orders, get_user_referrals_count
    from keyboards.user_keyboards import get_profile_keyboard
    user = await get_user(session, message.from_user.id)
    if not user:
        await message.answer("Please send /start first.")
        return
    orders = await get_user_orders(session, user.telegram_id, limit=50)
    referrals_count = await get_user_referrals_count(session, user.telegram_id)
    text = (
        f"{ce(CustomEmojis.CROWN, '👑')} <b>CUSTOMER ACCOUNT DASHBOARD</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> <b>{message.from_user.full_name}</b>\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Telegram ID:</b> <code>{message.from_user.id}</code>\n"
        f"{ce(CustomEmojis.WALLET, '💳')} <b>Wallet Balance:</b> <code>{config.CURRENCY_SYMBOL}{user.balance:.2f}</code>\n"
        f"{ce(CustomEmojis.ORDERS, '📦')} <b>Completed Orders:</b> <code>{len(orders)}</code>\n"
        f"{ce(CustomEmojis.REFER, '🎁')} <b>Invited Referrals:</b> <code>{referrals_count}</code>\n"
        f"{ce(CustomEmojis.VERIFIED, '✨')} <b>Account Status:</b> <code>Verified VIP Customer</code>\n\n"
        f"{UI.SECTION_BAR}"
    )
    await message.answer(text, reply_markup=get_profile_keyboard())

@router.message(F.text.in_(["🚨  Support", "🚨 Support", "Support", "🛟 Support"]))
async def msg_btn_support(message: types.Message):
    text = (
        f"{ce(CustomEmojis.SUPPORT, '🛟')} <b>24/7 CUSTOMER SUPPORT HELPDESK</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"✦ <b>Official Support:</b> {config.SUPPORT_USERNAME}\n"
        f"✦ <b>Official Channel:</b> {config.CHANNEL_LINK}\n\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>All purchases come with a 100% money-back / replacement guarantee.</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬  Contact Support Agent", url=f"https://t.me/{config.SUPPORT_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
    ])
    await message.answer(text, reply_markup=kb)

@router.message(F.text.in_(["🌟  Refer & Earn", "🌟 Refer & Earn", "Refer & Earn", "Refer"]))
async def msg_btn_refer(message: types.Message, session: AsyncSession):
    bot_info = getattr(message.bot, '_cached_me', None) or await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    text = (
        f"{ce(CustomEmojis.REFER, '🎁')} <b>INVITE FRIENDS & EARN REWARDS</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Earn <b>{config.REFERRAL_BONUS_PERCENT}% wallet credit</b> on every purchase made by your invited friends!\n\n"
        f"{ce(CustomEmojis.REFER, '🔗')} <b>Your Exclusive Referral Link:</b>\n"
        f"<code>{ref_link}</code>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Share Referral Link", url=f"https://t.me/share/url?url={ref_link}&text=Join%20SAM%20Store%20for%20genuine%20OTT%20and%20AI%20subscriptions!")],
        [InlineKeyboardButton(text="◀️ Back to Main Menu", callback_data="nav_home")]
    ])
    await message.answer(text, reply_markup=kb)

@router.message(F.text.in_(["⚡  Admin Control Panel", "⚡ Admin Control Panel", "Admin"]))
async def msg_btn_admin(message: types.Message):
    if not config.is_admin(message.from_user.id):
        return
    from handlers.admin import cmd_admin
    # invoke admin command directly
    await message.answer("Redirecting to Admin Panel... Send /admin to view.")

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
            f"{ce(CustomEmojis.SPARKLE, 'ℹ️')} <b>Custom Emoji Extractor Tool</b>\n\n"
            "<b>How to use:</b>\n"
            "1. Send your Telegram Premium animated emojis in chat, then <b>reply to it</b> with <code>/getemoji</code>.\n"
            "2. Or type <code>/getemoji</code> followed by a space and all your premium emojis."
        )
        return

    chunk_size = 15
    chunks = [emoji_ids[i:i + chunk_size] for i in range(0, len(emoji_ids), chunk_size)]

    for idx, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            result = f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Detected Custom Emojis (Part {idx}/{len(chunks)} — {len(emoji_ids)} Total):</b>\n\n"
        else:
            result = f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Detected Telegram Premium Custom Emoji ID(s):</b>\n\n"

        for eid in chunk:
            result += (
                f"• <b>Emoji ID:</b> <code>{eid}</code>\n"
                f"  <b>Live Render:</b> <tg-emoji emoji-id=\"{eid}\">✨</tg-emoji>\n"
                f"  <b>HTML Code:</b> <code>&lt;tg-emoji emoji-id=\"{eid}\"&gt;✨&lt;/tg-emoji&gt;</code>\n\n"
            )

        if idx == len(chunks):
            result += "<i>Copy the HTML code to paste into any product title or description!</i>"

        await message.answer(result)
