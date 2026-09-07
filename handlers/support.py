"""
Post-Delivery Support & Issue Resolution Handler
Provides interactive order issue selection and generates 1-tap pre-filled Telegram deep links
so the admin receives the exact Order ID, product name, date, and issue without confusion.
"""
import logging
import urllib.parse
from typing import Optional
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Order, Variant, Product
from database.crud import get_variant, get_product, save_order_feedback
from utils.emojis import CustomEmojis, UI, ce, format_emoji
from utils.states import CustomerOrderStates
from utils.notifications import send_public_vouch_notification
from keyboards.user_keyboards import get_order_rating_keyboard, get_review_tags_keyboard
import config

logger = logging.getLogger(__name__)

router = Router()

async def _get_order_context(session: AsyncSession, order_id: int):
    """Helper to fetch full order, variant, and product context."""
    stmt = (
        select(Order)
        .options(
            selectinload(Order.variant).selectinload(Variant.product)
        )
        .where(Order.id == order_id)
    )
    res = await session.execute(stmt)
    order = res.scalar_one_or_none()

    prod_title = "Digital Subscription"
    var_name = "Standard Plan"
    date_str = "Recent"
    amount_str = f"{config.CURRENCY_SYMBOL}0"

    if order:
        date_str = order.created_at.strftime("%d %b %Y, %H:%M UTC") if order.created_at else "Recent"
        amount_str = f"{config.CURRENCY_SYMBOL}{order.amount:.0f}"
        if order.variant:
            var_name = order.variant.name
            if order.variant.product:
                prod_title = order.variant.product.title

    return order, prod_title, var_name, date_str, amount_str


@router.callback_query(F.data.startswith("confirm_got_"))
async def cb_confirm_got(callback: types.CallbackQuery, session: AsyncSession):
    """Customer confirms they received the product."""
    await callback.answer("🎉 Great! Enjoy your subscription!", show_alert=True)
    order_id = int(callback.data.split("_")[2])

    # Send broadcast notification if not already sent
    try:
        order = await session.get(Order, order_id)
        if order and not getattr(order, "broadcast_sent", False):
            from database.crud import get_variant, get_product, get_available_stock_count
            from utils.notifications import send_order_notification
            variant = await get_variant(session, order.variant_id) if order.variant_id else None
            prod_title = "Product"
            var_name = ""
            if variant:
                product = await get_product(session, variant.product_id) if variant.product_id else None
                prod_title = product.title if product else "Product"
                var_name = variant.name or ""
                remaining = await get_available_stock_count(session, variant.id)
            else:
                remaining = 0

            bot: Bot = callback.bot
            bot_me = getattr(bot, '_cached_me', None) or await bot.get_me()
            await send_order_notification(
                bot=bot,
                order_id=order.id,
                buyer_name=callback.from_user.full_name or "Customer",
                product_title=prod_title,
                variant_name=var_name,
                amount=order.amount,
                stock_left=remaining,
                bot_username=bot_me.username or ""
            )
            order.broadcast_sent = True
            await session.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to send broadcast for order {order_id}: {e}")

    confirmed_text = (
        f"{ce(CustomEmojis.CHECK, '✅')} <b>ORDER #{order_id} — DELIVERY CONFIRMED</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>Glad you received your subscription!</b>\n"
        f"Thank you for shopping with <b>{config.STORE_NAME}</b>!\n\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Your warranty is active. Credentials remain permanently saved in Order History.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="View in Order History", callback_data="view_orders", icon_custom_emoji_id=CustomEmojis.ORDERS)],
        [InlineKeyboardButton(text="Continue Shopping", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
        [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])

    try:
        await callback.message.edit_text(confirmed_text, reply_markup=kb)
    except Exception:
        await callback.message.answer(confirmed_text, reply_markup=kb)


@router.callback_query(F.data.startswith("need_help_"))
async def cb_need_help(callback: types.CallbackQuery, session: AsyncSession):
    """Customer selects an issue for a specific order."""
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    order, prod_title, var_name, date_str, amount_str = await _get_order_context(session, order_id)

    help_text = (
        f"{ce(CustomEmojis.SUPPORT, '🛟')} <b>CUSTOMER SUPPORT HELPDESK</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order Reference:</b> <code>#{order_id}</code>\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b> ({var_name})\n"
        f"{ce(CustomEmojis.STAR, '📅')} <b>Ordered On:</b> {date_str}\n\n"
        f"<i>Please select the specific issue you are experiencing:</i>"
    )

    clean_sup = config.SUPPORT_USERNAME.lstrip('@')
    default_msg = f"Hello Support,\nI need help with Order #{order_id} ({prod_title} - {var_name}).\n\nDetails: "
    default_url = f"https://t.me/{clean_sup}?text={urllib.parse.quote(default_msg)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Login / Password Problem",
            callback_data=f"help_access_{order_id}",
            icon_custom_emoji_id=CustomEmojis.KEY
        )],
        [InlineKeyboardButton(
            text="Warranty Replacement",
            callback_data=f"help_replace_{order_id}",
            icon_custom_emoji_id=CustomEmojis.WARRANTY
        )],
        [InlineKeyboardButton(
            text="Payment / Billing Issue",
            callback_data=f"help_payment_{order_id}",
            icon_custom_emoji_id=CustomEmojis.WALLET
        )],
        [InlineKeyboardButton(
            text="Chat with Support Agent",
            url=default_url,
            icon_custom_emoji_id=CustomEmojis.SUPPORT
        )],
        [InlineKeyboardButton(
            text="Back to Order Receipt",
            callback_data=f"orderdetail_{order_id}",
            icon_custom_emoji_id=CustomEmojis.CROWN
        )]
    ])

    try:
        await callback.message.edit_text(help_text, reply_markup=kb)
    except Exception:
        await callback.message.answer(help_text, reply_markup=kb)


@router.callback_query(F.data.startswith("help_replace_"))
async def cb_help_replace(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    order, prod_title, var_name, date_str, amount_str = await _get_order_context(session, order_id)

    clean_sup = config.SUPPORT_USERNAME.lstrip('@')
    prefilled_msg = (
        f"Hello Support,\n"
        f"I would like to request a replacement for:\n\n"
        f"• Order ID: #{order_id}\n"
        f"• Product: {prod_title} ({var_name})\n"
        f"• Ordered On: {date_str}\n\n"
        f"Issue: Account credentials expired / not working under warranty."
    )
    direct_url = f"https://t.me/{clean_sup}?text={urllib.parse.quote(prefilled_msg)}"

    text = (
        f"{ce(CustomEmojis.WARRANTY, '🔄')} <b>REPLACEMENT REQUEST — ORDER #{order_id}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {var_name}\n"
        f"{ce(CustomEmojis.STAR, '📅')} <b>Ordered:</b> {date_str}\n\n"
        f"Tap <b>'Connect with Admin'</b> below. Your Order ID and replacement details are <b>pre-written in your chat box</b> so support can send replacement credentials immediately!\n\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <i>Typical agent response time: 5–15 minutes.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Connect with Admin (Pre-filled)",
            url=direct_url,
            icon_custom_emoji_id=CustomEmojis.SUPPORT
        )],
        [InlineKeyboardButton(text="Back to Issue Menu", callback_data=f"need_help_{order_id}", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("help_payment_"))
async def cb_help_payment(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    order, prod_title, var_name, date_str, amount_str = await _get_order_context(session, order_id)

    clean_sup = config.SUPPORT_USERNAME.lstrip('@')
    prefilled_msg = (
        f"Hello Support,\n"
        f"I have a payment/billing query for:\n\n"
        f"• Order ID: #{order_id}\n"
        f"• Product: {prod_title} ({var_name})\n"
        f"• Amount: {amount_str}\n\n"
        f"Issue: Payment verification / refund query."
    )
    direct_url = f"https://t.me/{clean_sup}?text={urllib.parse.quote(prefilled_msg)}"

    text = (
        f"{ce(CustomEmojis.WALLET, '💳')} <b>PAYMENT / BILLING QUERY — ORDER #{order_id}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {var_name}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> {amount_str}\n\n"
        f"Tap <b>'Connect with Admin'</b> below. Your payment reference and Order ID will be <b>automatically attached</b> to your message."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Connect with Admin (Pre-filled)",
            url=direct_url,
            icon_custom_emoji_id=CustomEmojis.WALLET
        )],
        [InlineKeyboardButton(text="Back to Issue Menu", callback_data=f"need_help_{order_id}", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("help_access_"))
async def cb_help_access(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    order, prod_title, var_name, date_str, amount_str = await _get_order_context(session, order_id)

    clean_sup = config.SUPPORT_USERNAME.lstrip('@')
    prefilled_msg = (
        f"Hello Support,\n"
        f"I am having a login/access issue with:\n\n"
        f"• Order ID: #{order_id}\n"
        f"• Product: {prod_title} ({var_name})\n\n"
        f"Issue: Unable to sign in with delivered credentials / PIN."
    )
    direct_url = f"https://t.me/{clean_sup}?text={urllib.parse.quote(prefilled_msg)}"

    text = (
        f"{ce(CustomEmojis.KEY, '🔑')} <b>LOGIN / ACCESS ISSUE — ORDER #{order_id}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>Quick Troubleshooting Tips:</b>\n"
        f"1️⃣ Tap the code box in Order History to copy credentials.\n"
        f"2️⃣ Try signing in in an Incognito / Private browser window.\n"
        f"3️⃣ Ensure no VPN is altering your region settings.\n\n"
        f"<b>Still unable to log in?</b> Tap below to connect with an agent with your order details pre-filled:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Connect with Admin (Pre-filled)",
            url=direct_url,
            icon_custom_emoji_id=CustomEmojis.KEY
        )],
        [InlineKeyboardButton(text="View Order Receipt", callback_data=f"orderdetail_{order_id}", icon_custom_emoji_id=CustomEmojis.ORDERS)],
        [InlineKeyboardButton(text="Back to Issue Menu", callback_data=f"need_help_{order_id}", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


# ==========================================
# CUSTOMER RATING & PUBLIC VOUCH SYSTEM
# ==========================================

TAG_MAP = {
    "fast": "⚡ Fast Delivery",
    "smooth": "🔥 Smooth Activation",
    "value": "👑 Best Value",
    "genuine": "🛡️ 100% Genuine"
}

@router.callback_query(F.data.startswith("rate_order_"))
async def cb_rate_order(callback: types.CallbackQuery, session: AsyncSession):
    """Customer initiates rating for an order."""
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    order = await session.get(Order, order_id)
    if not order:
        await callback.message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Order not found.")
        return

    if getattr(order, "rating", None):
        stars_str = "⭐" * int(order.rating)
        await callback.answer(f"You already rated this order with {stars_str}! Thank you!", show_alert=True)
        return

    text = (
        f"{ce(CustomEmojis.STAR, '⭐')} <b>RATE YOUR EXPERIENCE</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order Reference:</b> <code>#{order_id}</code>\n\n"
        f"How would you rate your subscription activation?\n"
        f"Your verified review will be officially published to our community Vouch Channel!"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_order_rating_keyboard(order_id))
    except Exception:
        await callback.message.answer(text, reply_markup=get_order_rating_keyboard(order_id))


@router.callback_query(F.data.startswith("rate_val_"))
async def cb_rate_val(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Customer selects star rating (e.g. 5, 4, 3 stars)."""
    await callback.answer()
    parts = callback.data.split("_")
    order_id = int(parts[2])
    stars = int(parts[3])

    await state.update_data(rate_order_id=order_id, rate_stars=stars, rate_tags=[])

    stars_display = "⭐" * stars
    text = (
        f"{ce(CustomEmojis.STAR, '⭐')} <b>YOUR RATING: {stars_display} ({stars}/5)</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Tap any compliments below that describe your experience, or add a written note:\n"
        f"<i>(When ready, click <b>🚀 Submit Review</b> below)</i>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_review_tags_keyboard(order_id, stars, []))
    except Exception:
        await callback.message.answer(text, reply_markup=get_review_tags_keyboard(order_id, stars, []))


@router.callback_query(F.data.startswith("rate_tag_"))
async def cb_rate_tag(callback: types.CallbackQuery, state: FSMContext):
    """Toggle a compliment tag in review."""
    await callback.answer()
    parts = callback.data.split("_")
    order_id = int(parts[2])
    code = parts[3]
    tag_label = TAG_MAP.get(code, code)

    data = await state.get_data()
    stars = data.get("rate_stars", 5)
    selected_tags = list(data.get("rate_tags", []))

    if tag_label in selected_tags:
        selected_tags.remove(tag_label)
    else:
        selected_tags.append(tag_label)

    await state.update_data(rate_tags=selected_tags)

    stars_display = "⭐" * stars
    tags_preview = " • ".join(selected_tags) if selected_tags else "<i>None selected yet</i>"
    text = (
        f"{ce(CustomEmojis.STAR, '⭐')} <b>YOUR RATING: {stars_display} ({stars}/5)</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>Selected Highlights:</b> {tags_preview}\n\n"
        f"Tap tags to toggle, add a written note, or click <b>🚀 Submit Review</b>:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_review_tags_keyboard(order_id, stars, selected_tags))
    except Exception:
        await callback.message.answer(text, reply_markup=get_review_tags_keyboard(order_id, stars, selected_tags))


@router.callback_query(F.data.startswith("rate_write_"))
async def cb_rate_write(callback: types.CallbackQuery, state: FSMContext):
    """Customer wants to type a custom written review."""
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    await state.set_state(CustomerOrderStates.waiting_for_review_text)
    await state.update_data(rate_order_id=order_id)

    prompt = (
        f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>LEAVE A WRITTEN REVIEW</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Please reply directly to this message with a short note or comment about your experience:\n\n"
        f"<i>(Example: 'Instant delivery, worked smoothly on my device! Recommended.')</i>"
    )
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Skip Note & Submit", callback_data=f"rate_sub_{order_id}", icon_custom_emoji_id=CustomEmojis.CHECK)]
    ])
    await callback.message.answer(prompt, reply_markup=cancel_kb)


@router.message(CustomerOrderStates.waiting_for_review_text, F.text)
async def msg_cust_review_text(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Customer submits their written review note."""
    review_content = message.text.strip()
    data = await state.get_data()
    order_id = data.get("rate_order_id")
    stars = data.get("rate_stars", 5)
    selected_tags = list(data.get("rate_tags", []))
    await state.clear()

    if not order_id:
        await message.answer("Review session expired. You can review from your Order History.")
        return

    await _finalize_and_publish_review(
        target_obj=message,
        bot=bot,
        session=session,
        order_id=order_id,
        stars=stars,
        tags=selected_tags,
        review_text=review_content,
        user=message.from_user,
        is_callback=False
    )


@router.callback_query(F.data.startswith("rate_sub_"))
async def cb_rate_sub(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    """Customer submits review directly."""
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    stars = data.get("rate_stars", 5)
    selected_tags = list(data.get("rate_tags", []))
    await state.clear()

    await _finalize_and_publish_review(
        target_obj=callback.message,
        bot=bot,
        session=session,
        order_id=order_id,
        stars=stars,
        tags=selected_tags,
        review_text=None,
        user=callback.from_user,
        is_callback=True
    )


async def _finalize_and_publish_review(
    target_obj,
    bot: Bot,
    session: AsyncSession,
    order_id: int,
    stars: int,
    tags: list[str],
    review_text: Optional[str],
    user: types.User,
    is_callback: bool = False
):
    tags_str = ", ".join(tags) if tags else None
    order = await save_order_feedback(session, order_id, stars, tags_str, review_text)
    if not order:
        await target_obj.answer("Order not found.")
        return

    # Publish public vouch to configured channel
    order_ctx, prod_title, var_name, _, _ = await _get_order_context(session, order_id)
    bot_me = getattr(bot, '_cached_me', None) or await bot.get_me()

    if not getattr(order, "vouch_sent", False):
        try:
            await send_public_vouch_notification(
                bot=bot,
                order_id=order.id,
                buyer_name=user.full_name or "Customer",
                username=user.username,
                product_title=prod_title,
                variant_name=var_name,
                rating=stars,
                review_tags=tags_str,
                review_text=review_text,
                bot_username=bot_me.username or ""
            )
            order.vouch_sent = True
            await session.commit()
        except Exception as e:
            logger.warning(f"Failed to post public vouch for order {order_id}: {e}")

    stars_display = "⭐" * stars
    thank_you_text = (
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>THANK YOU FOR YOUR VERIFIED REVIEW!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.STAR, '⭐')} <b>Your Rating:</b> <b>{stars_display} ({stars}/5)</b>\n"
        f"Your vouch has been recorded and officially published to our community channel!\n\n"
        f"{ce(CustomEmojis.HEART, '❤️')} <i>We appreciate your support and look forward to serving you again!</i>"
    )
    vouch_link = config.FEEDBACK_CHANNEL_LINK
    buttons = []
    if vouch_link:
        buttons.append([InlineKeyboardButton(text="🌟 View in Vouch Channel", url=vouch_link, icon_custom_emoji_id=CustomEmojis.FIRE)])
    buttons.append([
        InlineKeyboardButton(text="Continue Shopping", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP),
        InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if is_callback:
        try:
            await target_obj.edit_text(thank_you_text, reply_markup=kb)
        except Exception:
            await target_obj.answer(thank_you_text, reply_markup=kb)
    else:
        await target_obj.answer(thank_you_text, reply_markup=kb)


