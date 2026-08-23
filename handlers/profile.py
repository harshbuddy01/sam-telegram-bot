from aiogram import Router, F, types, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, get_user_orders, get_user_referrals_count, get_variant, get_product
from database.models import Order
from keyboards.user_keyboards import get_profile_keyboard, get_orders_list_keyboard, get_back_button
from utils.emojis import Emojis
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
    joined_date_str = user.joined_at.strftime("%Y-%m-%d")

    text = (
        f"👤 <b>USER ACCOUNT PROFILE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>User ID:</b> <code>{user.telegram_id}</code>\n"
        f"👤 <b>Name:</b> {user.full_name}\n"
        f"💰 <b>Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n"
        f"💳 <b>Total Spent:</b> {config.CURRENCY_SYMBOL}{user.total_spent:.2f}\n"
        f"📜 <b>Total Orders:</b> {len(orders)}\n"
        f"🎁 <b>Active Referrals:</b> {referrals_count} users\n"
        f"📅 <b>Joined Date:</b> {joined_date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Manage your balance and review previous purchases below:</i>"
    )

    await callback.message.edit_text(text, reply_markup=get_profile_keyboard())

@router.callback_query(F.data == "view_orders")
async def cb_view_orders(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    orders = await get_user_orders(session, callback.from_user.id, limit=10)

    if not orders:
        text = (
            f"📜 <b>ORDER HISTORY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"You haven't placed any orders yet.\n\n"
            f"Browse our catalog to make your first purchase!"
        )
        await callback.message.edit_text(text, reply_markup=get_back_button("nav_profile"))
        return

    text = (
        f"📜 <b>YOUR RECENT ORDERS (Last {len(orders)})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Click on any order below to view the credentials & details:\n"
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
        f"🧾 <b>ORDER SUMMARY #{order.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Item:</b> {prod_title}\n"
        f"✨ <b>Plan:</b> {var_name}\n"
        f"💰 <b>Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
        f"📅 <b>Purchased On:</b> {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 <b>DELIVERED CREDENTIALS / CODE:</b>\n"
        f"<pre><code>{order.delivered_content}</code></pre>\n"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{Emojis.BACK} Back to Orders", callback_data="view_orders")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "nav_refer")
async def cb_nav_refer(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer()
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    referrals_count = await get_user_referrals_count(session, callback.from_user.id)

    text = (
        f"🎁 <b>REFER & EARN PROGRAM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Earn <b>{config.REFERRAL_BONUS_PERCENT}% cash commission</b> every time your friend completes a purchase!\n\n"
        f"👥 <b>Your Total Referrals:</b> {referrals_count} members\n"
        f"🔗 <b>Your Exclusive Referral Link:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Share this link in your channels, groups, or with friends. Balance is added directly to your wallet on every order they place!</i>"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Get%20discounted%20OTT%20subscriptions%20instantly!")],
        [InlineKeyboardButton(text=f"{Emojis.BACK} Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
