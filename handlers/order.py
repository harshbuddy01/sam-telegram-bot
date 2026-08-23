from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_user,
    get_variant,
    get_product,
    fulfill_order,
    create_manual_order,
    get_available_stock_count
)
from utils.states import OrderManualStates
from utils.emojis import Emojis, UI, format_emoji, CustomEmojis, ce
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config

router = Router()

@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_variant(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
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
    prod_title = product.title if product else "Digital Item"
    prod_icon = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id) if product else "📦"

    # 1. Check Wallet Balance
    if user.balance < variant.price:
        shortfall = round(variant.price - user.balance, 2)
        text = (
            f"❌ <b>INSUFFICIENT WALLET BALANCE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Item:</b> {prod_icon} {prod_title} — <code>{variant.name}</code>\n"
            f"💰 <b>Plan Price:</b> {config.CURRENCY_SYMBOL}{variant.price:.2f}\n"
            f"{ce(CustomEmojis.WALLET, '💳')} <b>Your Balance:</b> {config.CURRENCY_SYMBOL}{user.balance:.2f}\n"
            f"⚠️ <b>Shortfall:</b> {config.CURRENCY_SYMBOL}{shortfall:.2f}\n\n"
            f"<i>Please top up your wallet balance via UPI to complete this purchase.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"➕ Deposit {config.CURRENCY_SYMBOL}{shortfall:.0f}+", callback_data="nav_deposit")],
            [InlineKeyboardButton(text="◀️ Back to Plan", callback_data=f"var_{variant.id}")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        return

    # 2. Check Fulfillment Mode (MANUAL vs AUTOMATIC)
    is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")

    if is_manual:
        # Prompt customer for email/details
        await state.set_state(OrderManualStates.waiting_for_input)
        await state.update_data(
            variant_id=variant.id,
            price=variant.price,
            prod_title=prod_title,
            var_name=variant.name,
            dispatch_time=getattr(variant, "manual_dispatch_time", "1–2 Hours") or "1–2 Hours"
        )

        prompt_msg = getattr(variant, "input_prompt", None) or "Please send your target Email / Account username for activation:"
        text = (
            f"✍️ <b>ACTIVATION DETAILS REQUIRED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Product:</b> {prod_icon} {prod_title}\n"
            f"✨ <b>Plan:</b> <b>{variant.name}</b>\n"
            f"💰 <b>Price:</b> <b>{config.CURRENCY_SYMBOL}{variant.price:.2f}</b>\n"
            f"⏱️ <b>Dispatch Time:</b> within {getattr(variant, 'manual_dispatch_time', '1–2 Hours')}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 <b>{prompt_msg}</b>\n\n"
            f"<i>(Reply to this message with your details to complete your order)</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️  Cancel & Go Back", callback_data=f"var_{variant.id}")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        return

    # 3. AUTOMATIC Fulfillment (Draws 1 stock from inventory)
    order, error_msg = await fulfill_order(session, user.telegram_id, variant.id, variant.price)
    
    if error_msg or not order:
        await callback.message.answer(
            f"⚠️ <b>Purchase Error:</b> {error_msg or 'Unknown error occurred.'}",
            show_alert=True
        )
        return

    remaining_stock = await get_available_stock_count(session, variant.id)

    delivery_text = (
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>ORDER #{order.id} COMPLETED & DELIVERED!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Product:</b> {prod_icon} {prod_title}\n"
        f"✨ <b>Plan:</b> <b>{variant.name}</b>\n"
        f"💰 <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
        f"💳 <b>Remaining Balance:</b> {config.CURRENCY_SYMBOL}{user.balance - order.amount:.2f}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>YOUR DELIVERED ACCOUNT / CODE:</b>\n"
        f"<i>(Tap the box below to copy automatically)</i>\n\n"
        f"<pre><code>{order.delivered_content}</code></pre>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Warranty Guidelines:</b>\n"
        f"✦ Do not edit account master email or passwords.\n"
        f"✦ Saved permanently in <b>Order History</b>.\n"
        f"✦ For replacement support, contact {config.SUPPORT_USERNAME}\n\n"
        f"❤️ <i>Thank you for shopping with {config.STORE_NAME}!</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦  View in Order History", callback_data="view_orders")],
        [InlineKeyboardButton(text="🛍️  Continue Shopping", callback_data="nav_shop")],
        [InlineKeyboardButton(text="🏠  Main Menu", callback_data="nav_home")]
    ])

    await callback.message.edit_text(delivery_text, reply_markup=kb)

    # Admin Alert for Instant Sale
    admin_alert = (
        f"🔔 <b>NEW AUTO-DELIVERED SALE!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
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

@router.message(OrderManualStates.waiting_for_input)
async def msg_order_manual_input(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    cust_input = message.text.strip()
    data = await state.get_data()
    variant_id = data.get("variant_id")
    price = data.get("price")
    prod_title = data.get("prod_title", "Digital Item")
    var_name = data.get("var_name", "Plan")
    dispatch_time = data.get("dispatch_time", "1–2 Hours")
    await state.clear()

    order, error_msg = await create_manual_order(
        session=session,
        user_id=message.from_user.id,
        variant_id=variant_id,
        amount=price,
        customer_input=cust_input
    )

    if error_msg or not order:
        await message.answer(f"⚠️ <b>Order Error:</b> {error_msg or 'Could not place order.'}")
        return

    # Customer Confirmation Receipt
    user = await get_user(session, message.from_user.id)
    receipt_text = (
        f"{ce(CustomEmojis.SPARKLE, '⏳')} <b>ORDER #{order.id} RECEIVED — MANUAL ACTIVATION</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Product:</b> {prod_title}\n"
        f"✨ <b>Plan:</b> <code>{var_name}</code>\n"
        f"💰 <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
        f"📧 <b>Target Details:</b> <code>{order.customer_input}</code>\n"
        f"⏱️ <b>Expected Dispatch:</b> Within {dispatch_time}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Our administration is processing your activation. You will receive an instant Telegram notification with your login/invite link as soon as it is dispatched!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 View Order Status", callback_data=f"orderdetail_{order.id}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
    ])
    await message.answer(receipt_text, reply_markup=kb)

    # Admin High-Priority Alert with 1-Click Fulfill & Refund Buttons
    admin_text = (
        f"🚨 <b>NEW MANUAL ORDER #{order.id} REQUIRING DISPATCH!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Customer:</b> {message.from_user.full_name} (@{message.from_user.username or 'NoUser'})\n"
        f"🆔 <b>User ID:</b> <code>{message.from_user.id}</code>\n"
        f"📦 <b>Item:</b> {prod_title} — {var_name}\n"
        f"💰 <b>Amount:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
        f"📧 <b>Customer Input:</b> <code>{order.customer_input}</code>\n"
        f"⏱️ <b>Expected Within:</b> {dispatch_time}\n\n"
        f"<i>Click below to fulfill and deliver the credentials or refund:</i>"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Fulfill & Send Credentials", callback_data=f"adm_man_ful_{order.id}")],
        [InlineKeyboardButton(text="❌ Cancel & Refund Wallet", callback_data=f"adm_man_ref_{order.id}")]
    ])
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=admin_kb)
        except Exception:
            pass
