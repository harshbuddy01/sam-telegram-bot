from aiogram import Router, F, types, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_user,
    get_variant,
    get_product,
    fulfill_order,
    get_available_stock_count
)
from utils.emojis import Emojis, UI
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config

router = Router()

@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_variant(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer()
    variant_id = int(callback.data.split("_")[1])
    variant = await get_variant(session, variant_id)

    if not variant:
        await callback.message.answer("Selected plan was not found.")
        return

    user = await get_user(session, callback.from_user.id)
    if not user:
        await callback.message.answer("User profile not found. Please type /start.")
        return

    product = await get_product(session, variant.product_id)

    # Check balance
    if user.balance < variant.price:
        shortfall = round(variant.price - user.balance, 2)
        text = (
            f"❌ <b>INSUFFICIENT WALLET BALANCE</b>\n"
            f"{UI.SECTION_BAR}\n\n"
            f"<blockquote>"
            f"📦 <b>Item:</b> {product.title if product else 'Product'} — {variant.name}\n"
            f"💰 <b>Plan Price:</b> {config.CURRENCY_SYMBOL}{variant.price:.2f}\n"
            f"💳 <b>Your Balance:</b> {config.CURRENCY_SYMBOL}{user.balance:.2f}\n"
            f"⚠️ <b>Shortfall:</b> {config.CURRENCY_SYMBOL}{shortfall:.2f}"
            f"</blockquote>\n\n"
            f"<i>Please top up your wallet via UPI to complete this purchase.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"➕ Deposit {config.CURRENCY_SYMBOL}{shortfall:.0f}+", callback_data="nav_deposit")],
            [InlineKeyboardButton(text="◀️ Back to Plan", callback_data=f"var_{variant.id}")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        return

    # Attempt fulfillment
    order, error_msg = await fulfill_order(session, user.telegram_id, variant.id, variant.price)
    
    if error_msg or not order:
        await callback.message.answer(
            f"⚠️ <b>Purchase Error:</b> {error_msg or 'Unknown error occurred.'}",
            show_alert=True
        )
        return

    # Delivery Card
    remaining_stock = await get_available_stock_count(session, variant.id)
    prod_title = product.title if product else "Digital Item"

    delivery_text = (
        f"🎉 <b>ORDER #{order.id} COMPLETED & DELIVERED!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"📦 <b>Product:</b> {prod_title}\n"
        f"✨ <b>Plan:</b> {variant.name}\n"
        f"💰 <b>Amount Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
        f"💳 <b>Wallet Remaining:</b> {config.CURRENCY_SYMBOL}{user.balance - order.amount:.2f}"
        f"</blockquote>\n\n"
        f"🔑 <b>YOUR DELIVERED ACCOUNT / CODE:</b>\n"
        f"<i>(Tap the box below to copy automatically)</i>\n\n"
        f"<pre><code>{order.delivered_content}</code></pre>\n\n"
        f"<blockquote>"
        f"🛡️ <b>Warranty Guidelines:</b>\n"
        f"✦ Do not edit account details or profile pins.\n"
        f"✦ Saved permanently in <b>My Profile > Orders</b>.\n"
        f"✦ For support or warranty, contact {config.SUPPORT_USERNAME}"
        f"</blockquote>\n\n"
        f"❤️ <i>Thank you for choosing {config.UPI_NAME}!</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜  View in Order History", callback_data="view_orders")],
        [InlineKeyboardButton(text="🛒  Continue Shopping", callback_data="nav_shop")],
        [InlineKeyboardButton(text="🏠  Main Menu", callback_data="nav_home")]
    ])

    await callback.message.edit_text(delivery_text, reply_markup=kb)

    # Admin Alert
    admin_alert = (
        f"🔔 <b>NEW SALE NOTIFICATION!</b>\n"
        f"{UI.SECTION_BAR}\n"
        f"🧾 <b>Order ID:</b> #{order.id}\n"
        f"👤 <b>Customer:</b> {callback.from_user.full_name} (@{callback.from_user.username or 'NoUser'})\n"
        f"🆔 <b>User ID:</b> <code>{callback.from_user.id}</code>\n"
        f"📦 <b>Item:</b> {prod_title} — {variant.name}\n"
        f"💰 <b>Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
        f"📊 <b>Remaining Stock:</b> {remaining_stock} available"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_alert)
        except Exception:
            pass
