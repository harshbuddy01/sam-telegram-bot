from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, get_user_orders, get_user_referrals_count, get_variant, get_product
from database.models import Order
from keyboards.user_keyboards import get_profile_keyboard, get_orders_list_keyboard, get_back_button
from utils.emojis import Emojis, UI, CustomEmojis, ce, format_emoji
from utils.templates import render_template
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

    text = await render_template(
        session,
        "profile_text",
        user_name=user.full_name,
        user_id=user.telegram_id,
        currency=config.CURRENCY_SYMBOL,
        balance=f"{user.balance:.2f}",
        total_spent=f"{user.total_spent:.2f}",
        order_count=len(orders),
        referral_percent=config.REFERRAL_BONUS_PERCENT
    )

    await callback.message.edit_text(text, reply_markup=get_profile_keyboard())

@router.callback_query(F.data == "view_orders")
async def cb_view_orders(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    orders = await get_user_orders(session, callback.from_user.id, limit=10)

    if not orders:
        text = (
            f"{ce(CustomEmojis.ORDERS, '📦')} <b>YOUR ORDER HISTORY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{ce(CustomEmojis.SPARKLE, 'ℹ️')} <i>You haven't made any purchases yet.</i>\n\n"
            f"Explore our store to buy genuine subscriptions with instant automated delivery!"
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️  Explore Store Now", callback_data="nav_shop")],
            [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        return

    orders_icon = ce(CustomEmojis.ORDERS, "📦")
    text = (
        f"{orders_icon} <b>YOUR ORDER HISTORY (Recent {len(orders)})</b>\n"
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
    prod_icon = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id) if product else "📦"
    var_name = variant.name if variant else "Standard Plan"
    date_str = order.created_at.strftime("%d %b %Y, %H:%M UTC")

    status = getattr(order, "status", "COMPLETED")
    key_icon = ce(CustomEmojis.KEY, "🔑")
    warranty_icon = ce(CustomEmojis.WARRANTY, "🛡️")
    
    if status == "COMPLETED":
        status_line = "🟢 <b>Status:</b> Completed & Delivered"
        middle_block = (
            f"{key_icon} <b>DELIVERED CREDENTIALS / KEY:</b>\n"
            f"<pre><code>{order.delivered_content}</code></pre>\n"
        )
        footer_line = f"{warranty_icon} <i>Under 100% Replacement Warranty! Contact support ({config.SUPPORT_USERNAME}) for help.</i>"
    elif status == "PENDING_DISPATCH":
        status_line = "⏳ <b>Status:</b> In Progress (Manual Activation within 1–2h)"
        middle_block = (
            f"{ce(CustomEmojis.VERIFIED, '📧')} <b>Provided Target Details:</b>\n"
            f"<code>{order.customer_input or 'None'}</code>\n\n"
            f"{ce(CustomEmojis.FIRE, '⏱️')} <i>Our administration is processing your activation. Credentials will be delivered here automatically!</i>\n"
        )
        footer_line = f"{ce(CustomEmojis.SUPPORT, '💬')} <i>Need expedited delivery? Contact support: {config.SUPPORT_USERNAME}</i>"
    else:
        status_line = "❌ <b>Status:</b> Cancelled & Refunded to Wallet"
        middle_block = (
            f"{ce(CustomEmojis.WALLET, '💰')} <i>Amount <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b> has been credited back to your wallet balance.</i>\n"
        )
        footer_line = f"{ce(CustomEmojis.SUPPORT, '💬')} <i>Contact support ({config.SUPPORT_USERNAME}) if you have any questions.</i>"

    text = (
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>ORDER RECEIPT #{order.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_icon} {prod_title}\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{var_name}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
        f"{ce(CustomEmojis.STAR, '📅')} <b>Ordered On:</b> {date_str}\n"
        f"{status_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{middle_block}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{footer_line}"
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

    refer_icon = ce(CustomEmojis.REFER, "🎁")

    text = (
        f"{refer_icon} <b>INVITE & EARN PROGRAM</b> {refer_icon}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Share your referral link with friends and earn wallet rewards when they top up or buy!\n\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Per-Order Reward:</b> <b>{config.REFERRAL_BONUS_PERCENT}% Cash Commission</b>\n"
        f"{ce(CustomEmojis.TROPHY, '🎯')} <b>Requirement:</b> Unlimited earnings, credited automatically\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>YOUR REFERRAL STATS</b>\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Friends Invited:</b> {referrals_count}\n"
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Status:</b> Active & Earning\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.REFER, '🔗')} <b>YOUR EXCLUSIVE INVITE LINK:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"{ce(CustomEmojis.SPARKLE, '💡')} <i>Tip: Click the link above to copy it instantly.</i>"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢  Share With Friends", url=f"https://t.me/share/url?url={ref_link}&text=Get%20discounted%20OTT%20and%20AI%20subscriptions%20instantly%20on%20{config.STORE_NAME}!")],
        [InlineKeyboardButton(text="◀️  Back to Main Menu", callback_data="nav_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
