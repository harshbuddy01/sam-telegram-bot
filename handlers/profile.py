from aiogram import Router, F, types, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, get_user_orders, get_user_referrals_count, get_variant, get_product
from database.models import Order
from keyboards.user_keyboards import get_profile_keyboard, get_orders_list_keyboard, get_back_button
from utils.emojis import Emojis, UI
import config

router = Router()

@router.callback_query(F.data == "nav_profile")
async def cb_nav_profile(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer()
    user = await get_user(session, callback.from_user.id)
    if not user:
        await callback.message.answer("Profile not found. Please send /start.")
        return

    orders = await get_user_orders(session, user.telegram_id, limit=50)
    referrals_count = await get_user_referrals_count(session, user.telegram_id)
    joined_date_str = user.joined_at.strftime("%d %b %Y")

    text = (
        f"👤 <b>CUSTOMER ACCOUNT DASHBOARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"👤 <b>Name:</b> <b>{user.full_name}</b>\n"
        f"💰 <b>Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n"
        f"🛒 <b>Total Orders:</b> {len(orders)}\n"
        f"💳 <b>Total Spent:</b> {config.CURRENCY_SYMBOL}{user.total_spent:.2f}\n"
        f"👥 <b>Friends Invited:</b> {referrals_count}\n"
        f"📅 <b>Member Since:</b> {joined_date_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 <i>Manage your funds, view previous keys, or invite friends below:</i>"
    )

    await callback.message.edit_text(text, reply_markup=get_profile_keyboard())

@router.callback_query(F.data == "view_orders")
async def cb_view_orders(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    orders = await get_user_orders(session, callback.from_user.id, limit=10)

    if not orders:
        text = (
            f"📦 <b>YOUR ORDER HISTORY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"ℹ️ <i>You haven't made any purchases yet.</i>\n\n"
            f"Explore our store to buy genuine subscriptions with instant automated delivery!"
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️  Explore Store Now", callback_data="nav_shop")],
            [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        return

    text = (
        f"📦 <b>YOUR ORDER HISTORY (Recent {len(orders)})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Tap on any order below to inspect your delivered credentials, PINs & warranty info:\n"
    )

    await callback.message.edit_text(text, reply_markup=get_orders_list_keyboard(orders))

@router.callback_query(F.data.startswith("orderdetail_"))
async def cb_order_detail(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    order_id = int(callback.data.split("_")[1])
    
    from sqlalchemy import select
    res = await session.execute(select(Order).where(Order.id == order_id, Order.user_id == callback.from_user.id))
    order = res.scalar_one_or_none()

    if not order:
        await callback.message.answer("Order not found.")
        return

    variant = await get_variant(session, order.variant_id)
    product = await get_product(session, variant.product_id) if variant else None
    prod_title = product.title if product else "Digital Service"
    var_name = variant.name if variant else "Standard Plan"
    date_str = order.created_at.strftime("%d %b %Y, %H:%M UTC")

    text = (
        f"🧾 <b>ORDER RECEIPT #{order.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Product:</b> {prod_title}\n"
        f"✨ <b>Plan:</b> {var_name}\n"
        f"💰 <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
        f"📅 <b>Purchased On:</b> {date_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>DELIVERED CREDENTIALS / KEY:</b>\n"
        f"<pre><code>{order.delivered_content}</code></pre>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛡️ <i>Under 100% Replacement Warranty! Contact support for assistance.</i>"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️  Back to Order History", callback_data="view_orders")],
        [InlineKeyboardButton(text="🏠  Main Menu", callback_data="nav_home")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "nav_refer")
async def cb_nav_refer(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer()
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    referrals_count = await get_user_referrals_count(session, callback.from_user.id)

    text = (
        f"🎁 <b>INVITE & EARN PROGRAM</b> 🎁\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Share your referral link with friends and earn wallet rewards when they top up or buy!\n\n"
        f"💰 <b>Per-Order Reward:</b> <b>{config.REFERRAL_BONUS_PERCENT}% Cash Commission</b>\n"
        f"🎯 <b>Requirement:</b> Unlimited earnings, credited automatically\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>YOUR REFERRAL STATS</b>\n"
        f"👤 <b>Friends Invited:</b> {referrals_count}\n"
        f"✅ <b>Status:</b> Active & Earning\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>YOUR EXCLUSIVE INVITE LINK:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 <i>Tip: Click the link above to copy it instantly.</i>"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢  Share With Friends", url=f"https://t.me/share/url?url={ref_link}&text=Get%20discounted%20OTT%20and%20AI%20subscriptions%20instantly%20on%20SamStore!")],
        [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
