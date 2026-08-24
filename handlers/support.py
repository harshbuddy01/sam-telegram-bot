"""
Post-Delivery Support & Confirmation Handler
Handles 'I Got It' confirmations and 'I Need Help' support flows.
"""
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_order
from utils.emojis import CustomEmojis, ce
import config

router = Router()


@router.callback_query(F.data.startswith("confirm_got_"))
async def cb_confirm_got(callback: types.CallbackQuery):
    """Customer confirms they received the product."""
    await callback.answer("🎉 Great! Enjoy your subscription!", show_alert=True)
    order_id = int(callback.data.split("_")[2])

    confirmed_text = (
        f"{ce(CustomEmojis.CHECK, '✅')} <b>ORDER #{order_id} — DELIVERY CONFIRMED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>Glad you received your product!</b>\n"
        f"Enjoy your subscription and thank you for shopping with <b>{config.STORE_NAME}</b>!\n\n"
        f"{ce(CustomEmojis.SPARKLE, '💡')} <i>Your credentials are saved permanently in Order History.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 View in Order History", callback_data="view_orders", icon_custom_emoji_id=CustomEmojis.ORDERS)],
        [InlineKeyboardButton(text="🛍️ Continue Shopping", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])

    try:
        await callback.message.edit_text(confirmed_text, reply_markup=kb)
    except Exception:
        await callback.message.answer(confirmed_text, reply_markup=kb)


@router.callback_query(F.data.startswith("need_help_"))
async def cb_need_help(callback: types.CallbackQuery):
    """Customer needs help with their order."""
    await callback.answer()
    order_id = int(callback.data.split("_")[2])

    help_text = (
        f"{ce(CustomEmojis.SUPPORT, '❓')} <b>SUPPORT CENTER — ORDER #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"What issue are you facing? Select an option below:\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔄 Replacement Request",
            callback_data=f"help_replace_{order_id}",
            icon_custom_emoji_id=CustomEmojis.SPARKLE
        )],
        [InlineKeyboardButton(
            text="💳 Payment / Billing Issue",
            callback_data=f"help_payment_{order_id}",
            icon_custom_emoji_id=CustomEmojis.WALLET
        )],
        [InlineKeyboardButton(
            text="🔑 Login / Access Problem",
            callback_data=f"help_access_{order_id}",
            icon_custom_emoji_id=CustomEmojis.KEY
        )],
        [InlineKeyboardButton(
            text="💬 Chat with Support Agent",
            url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}",
            icon_custom_emoji_id=CustomEmojis.SUPPORT
        )],
        [InlineKeyboardButton(
            text="◀️ Back to Order",
            callback_data=f"orderdetail_{order_id}",
            icon_custom_emoji_id=CustomEmojis.CROWN
        )]
    ])

    try:
        await callback.message.edit_text(help_text, reply_markup=kb)
    except Exception:
        await callback.message.answer(help_text, reply_markup=kb)


@router.callback_query(F.data.startswith("help_replace_"))
async def cb_help_replace(callback: types.CallbackQuery):
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    text = (
        f"{ce(CustomEmojis.WARRANTY, '🔄')} <b>REPLACEMENT REQUEST — ORDER #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"To request a replacement, please contact our support team:\n\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Support:</b> {config.SUPPORT_USERNAME}\n\n"
        f"{ce(CustomEmojis.ORDERS, '📋')} <b>Include this info in your message:</b>\n"
        f"• Order ID: <code>#{order_id}</code>\n"
        f"• Issue: Account not working / expired\n"
        f"• Screenshot of the error (if any)\n\n"
        f"<i>Our team typically responds within 30 minutes!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💬 Message Support Now",
            url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}?text=Replacement%20Request%20for%20Order%20%23{order_id}"
        )],
        [InlineKeyboardButton(text="◀️ Back", callback_data=f"need_help_{order_id}")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("help_payment_"))
async def cb_help_payment(callback: types.CallbackQuery):
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    text = (
        f"{ce(CustomEmojis.WALLET, '💳')} <b>PAYMENT ISSUE — ORDER #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"For payment or billing issues, please contact support:\n\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Support:</b> {config.SUPPORT_USERNAME}\n\n"
        f"{ce(CustomEmojis.ORDERS, '📋')} <b>Include this info:</b>\n"
        f"• Order ID: <code>#{order_id}</code>\n"
        f"• Payment screenshot / UTR number\n"
        f"• Description of the issue\n\n"
        f"<i>Refunds are processed within 24 hours.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💬 Message Support Now",
            url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}?text=Payment%20Issue%20for%20Order%20%23{order_id}"
        )],
        [InlineKeyboardButton(text="◀️ Back", callback_data=f"need_help_{order_id}")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("help_access_"))
async def cb_help_access(callback: types.CallbackQuery):
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    text = (
        f"{ce(CustomEmojis.KEY, '🔑')} <b>LOGIN / ACCESS ISSUE — ORDER #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Quick troubleshooting steps:</b>\n\n"
        f"1️⃣ Copy credentials from Order History (tap the code box)\n"
        f"2️⃣ Try logging in on a fresh browser / incognito window\n"
        f"3️⃣ Clear app cache if using mobile app\n"
        f"4️⃣ Do NOT change password or email\n\n"
        f"<b>Still not working?</b> Contact support with your Order ID:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💬 Message Support Now",
            url=f"https://t.me/{config.SUPPORT_USERNAME.lstrip('@')}?text=Access%20Issue%20for%20Order%20%23{order_id}"
        )],
        [InlineKeyboardButton(text="📦 View Order History", callback_data="view_orders")],
        [InlineKeyboardButton(text="◀️ Back", callback_data=f"need_help_{order_id}")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
