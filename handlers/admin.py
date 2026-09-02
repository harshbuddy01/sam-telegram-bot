import logging
from aiogram import Router, F, types, Bot

logger = logging.getLogger(__name__)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_all_users_count,
    get_all_user_ids,
    get_total_orders_and_revenue,
    get_orders_today_count,
    get_total_active_stock,
    get_pending_deposits,
    get_deposit,
    approve_deposit,
    reject_deposit,
    get_all_categories,
    get_category,
    create_category,
    update_category_details,
    delete_category,
    get_products_by_category,
    get_all_products,
    get_product,
    create_product,
    update_product_details,
    delete_product,
    get_variants_by_product,
    get_all_variants,
    get_variant,
    create_variant,
    update_variant_details,
    delete_variant,
    add_stock_bulk,
    get_available_stock_count,
    get_unsold_stock_by_variant,
    delete_unsold_stock_by_variant,
    get_pending_manual_orders,
    get_order_by_id,
    get_recent_orders,
    fulfill_manual_order,
    cancel_and_refund_order,
    get_user,
    update_user_balance,
    get_all_users_count,
    get_users_with_balance,
    get_recent_users,
    get_total_wallet_liabilities,
    search_users,
    get_all_deposits,
    get_deposits_stats,
    get_product,
    fulfill_order
)
from keyboards.admin_keyboards import (
    get_admin_main_keyboard,
    get_admin_recent_orders_keyboard,
    get_admin_order_audit_keyboard,
    get_admin_categories_keyboard,
    get_admin_category_edit_keyboard,
    get_admin_category_select_keyboard,
    get_admin_products_keyboard,
    get_admin_product_edit_keyboard,
    get_admin_product_select_keyboard,
    get_admin_variants_keyboard,
    get_admin_variant_edit_keyboard,
    get_admin_stock_inventory_keyboard,
    get_admin_variant_stock_actions_keyboard,
    get_admin_pending_orders_keyboard,
    get_admin_manual_order_detail_keyboard,
    get_deposit_approval_keyboard,
    get_admin_settings_keyboard,
    get_admin_gateway_settings_keyboard,
    get_admin_fulfillment_type_keyboard,
    get_admin_cancel_keyboard,
    get_admin_customizer_keyboard,
    get_admin_template_edit_keyboard,
    get_admin_users_hub_keyboard,
    get_admin_user_card_keyboard,
    get_admin_recent_users_keyboard
)
from utils.states import (
    AdminCategoryStates,
    AdminCategoryEditStates,
    AdminProductStates,
    AdminProductEditStates,
    AdminVariantStates,
    AdminVariantEditStates,
    AdminStockStates,
    AdminBroadcastStates,
    AdminUserManagementStates,
    AdminManualOrderStates,
    AdminSettingsStates,
    AdminTemplateStates
)
from utils.templates import (
    get_template,
    set_template,
    reset_template,
    TEMPLATE_METADATA,
    DEFAULT_TEMPLATES
)
from utils.emojis import (
    Emojis,
    UI,
    format_emoji,
    extract_clean_name_and_emoji,
    extract_emoji_and_custom_id,
    get_message_html_text,
    clean_button_text,
    CustomEmojis,
    ce
)
import config

router = Router()
router.message.filter(lambda message: config.is_admin(message.from_user.id))
router.callback_query.filter(lambda callback: config.is_admin(callback.from_user.id))

def check_admin(user_id: int) -> bool:
    return config.is_admin(user_id)

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext, session: AsyncSession):
    if not check_admin(message.from_user.id):
        return
    await state.clear()
    
    pending_deps = len(await get_pending_deposits(session))
    pending_orders = len(await get_pending_manual_orders(session))
    
    text = (
        f"{ce(CustomEmojis.CROWN, '👑')} <b>ADMINISTRATOR CONTROL PANEL</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<i>Select a management hub below to manage your store:</i>"
    )
    await message.answer(text, reply_markup=get_admin_main_keyboard(pending_deps, pending_orders))

@router.message(Command("addstock"))
async def cmd_addstock(message: types.Message, state: FSMContext, session: AsyncSession):
    if not check_admin(message.from_user.id):
        return
    await state.clear()
    variants = await get_all_variants(session)

    if not variants:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} No subscription plans found.")
        return

    stock_counts = {}
    for var in variants:
        stock_counts[var.id] = await get_available_stock_count(session, var.id)

    text = (
        f"{ce(CustomEmojis.KEY, '🔑')} <b>SELECT PLAN TO ADD STOCK</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<i>Click on any plan below to paste and upload accounts/keys:</i>\n"
    )
    await message.answer(text, reply_markup=get_admin_stock_inventory_keyboard(variants, stock_counts))

@router.callback_query(F.data == "admin_home")
async def cb_admin_home(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    
    pending_deps = len(await get_pending_deposits(session))
    pending_ords = len(await get_pending_manual_orders(session))
    
    text = (
        f"{ce(CustomEmojis.CROWN, '👑')} <b>ADMIN MANAGEMENT PANEL</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Welcome, Administrator <b>{callback.from_user.first_name}</b>.\n"
        f"<i>Select a management option below:</i>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_admin_main_keyboard(pending_deps, pending_ords))
    except Exception:
        await callback.message.answer(text, reply_markup=get_admin_main_keyboard(pending_deps, pending_ords))

# ================= 1. STORE STATISTICS =================

@router.callback_query(F.data == "adm_stats")
async def cb_admin_stats(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    total_users = await get_all_users_count(session)
    total_orders, total_sales = await get_total_orders_and_revenue(session)
    orders_today = await get_orders_today_count(session)
    total_stock = await get_total_active_stock(session)
    pending_deposits = len(await get_pending_deposits(session))
    pending_manual = len(await get_pending_manual_orders(session))

    text = (
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>LIVE STORE METRICS & ANALYTICS</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.VERIFIED, '👥')} <b>Registered Customers:</b> {total_users}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Gross Sales Revenue:</b> <b>{config.CURRENCY_SYMBOL}{total_sales:.2f}</b>\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>All-Time Orders:</b> {total_orders}\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Orders Today:</b> {orders_today}\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>Active Inventory:</b> {total_stock} in stock\n"
        f"{ce(CustomEmojis.ORDERS, '⏳')} <b>Pending Manual Orders:</b> {pending_manual}\n"
        f"{ce(CustomEmojis.WALLET, '💳')} <b>Pending Deposits:</b> {pending_deposits}"
        f"</blockquote>\n\n"
        f"{UI.SECTION_BAR}"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

# ================= 2. ALL ORDERS & SALES AUDIT LOGS =================

@router.callback_query(F.data == "adm_orders_log")
async def cb_admin_orders_log(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    orders = await get_recent_orders(session, limit=25)
    if not orders:
        text = (
            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>ALL ORDERS & SALES AUDIT LOG</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"ℹ️ <i>No customer orders placed yet in the database.</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))
        return

    text = (
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>RECENT ORDERS & SALES AUDIT LOG ({len(orders)})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Click any order below to inspect full database proof, customer details & delivered keys:\n"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_recent_orders_keyboard(orders))

@router.callback_query(F.data.startswith("adm_audit_"))
async def cb_admin_order_audit(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    order_id = int(callback.data.split("_")[2])
    order = await get_order_by_id(session, order_id)
    if not order:
        await callback.message.answer("Order record not found in database.")
        return

    user = order.user
    variant = order.variant
    product = await get_product(session, variant.product_id) if variant else None
    prod_title = product.title if product else "Digital Item"
    var_name = variant.name if variant else "Plan"
    date_str = order.created_at.strftime("%d %b %Y, %H:%M:%S UTC")

    status_badge = f"{ce(CustomEmojis.CHECK, '🟢')} COMPLETED (DELIVERED)" if order.status == "COMPLETED" else (f"{ce(CustomEmojis.FIRE, '⏳')} PENDING DISPATCH" if order.status == "PENDING_DISPATCH" else f"{ce(CustomEmojis.LOCK, '❌')} CANCELLED / REFUNDED")

    text = (
        f"{ce(CustomEmojis.SEARCH, '🔍')} <b>DATABASE ORDER AUDIT PROOF #{order.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer Name:</b> {user.full_name if user else 'Unknown'}\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Telegram ID:</b> <code>{order.user_id}</code>\n"
        f"{ce(CustomEmojis.SUPPORT, '💬')} <b>Username:</b> @{user.username or 'NoUsername' if user else 'None'}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Order Status:</b> {status_badge}\n"
        f"{ce(CustomEmojis.STAR, '📅')} <b>Timestamp:</b> {date_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_title}\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <code>{var_name}</code>\n"
        f"{ce(CustomEmojis.CARD, '📱')}/📧 <b>Customer Input (Phone/Email):</b>\n"
        f"<code>{order.customer_input or 'None (Auto Stock Plan)'}</code>\n\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>DELIVERED CREDENTIALS / CODE:</b>\n"
        f"<pre><code>{order.delivered_content or 'Pending dispatch'}</code></pre>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.CHECK, '✅')} <i>Verified Authentic Database Record</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_order_audit_keyboard(order.id))

# ================= 3. PENDING MANUAL ORDERS HUB =================

@router.callback_query(F.data == "adm_pending_orders")
async def cb_admin_pending_orders(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    orders = await get_pending_manual_orders(session)
    if not orders:
        text = (
            f"{ce(CustomEmojis.FIRE, '⏳')} <b>PENDING MANUAL ORDERS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{ce(CustomEmojis.CHECK, '✅')} <i>No pending manual orders right now! All orders have been dispatched.</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))
        return

    text = (
        f"{ce(CustomEmojis.FIRE, '⏳')} <b>PENDING MANUAL ORDERS ({len(orders)})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Click an order below to view customer input and deliver credentials/links:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_pending_orders_keyboard(orders))

@router.callback_query(F.data.startswith("adm_ord_view_"))
async def cb_admin_ord_view(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    order_id = int(callback.data.split("_")[3])
    order = await get_order_by_id(session, order_id)
    if not order:
        await callback.message.answer("Order not found.")
        return

    user = await get_user(session, order.user_id)
    variant = order.variant
    product = await get_product(session, variant.product_id) if variant else None
    prod_title = product.title if product else "Product"
    var_name = variant.name if variant else "Plan"
    qty = getattr(order, "quantity", 1) or 1
    qty_line = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""

    text = (
        f"📋 <b>MANUAL ORDER DETAILS #{order.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Customer:</b> {user.full_name if user else 'User'} (ID: <code>{order.user_id}</code>)\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Item:</b> {prod_title} — {var_name}{qty_line}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
        f"{ce(CustomEmojis.STAR, '📅')} <b>Ordered At:</b> {order.created_at.strftime('%d %b %Y, %H:%M UTC')}\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Status:</b> {ce(CustomEmojis.FIRE, '⏳')} PENDING DISPATCH\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 <b>CUSTOMER PROVIDED DETAILS:</b>\n"
        f"<code>{order.customer_input or 'None'}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Click 'Fulfill' to send the login details/link, or 'Cancel & Refund' to refund customer's balance:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_manual_order_detail_keyboard(order.id))

@router.callback_query(F.data.startswith("adm_man_ful_"))
async def cb_admin_man_ful(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    order_id = int(callback.data.split("_")[3])
    order = await get_order_by_id(session, order_id)
    await state.set_state(AdminManualOrderStates.waiting_for_fulfillment_content)
    await state.update_data(order_id=order_id)

    qty = getattr(order, "quantity", 1) or 1 if order else 1
    if qty > 1:
        qty_prompt = (
            f"⚠️ <b>ORDER FOR {qty} UNITS:</b>\n"
            f"Please enter the credentials for all {qty} accounts:\n\n"
            f"<code>Account 1:\nEmail: ...\nPassword: ...\n\nAccount 2:\nEmail: ...\nPassword: ...</code>\n\n"
        )
    else:
        qty_prompt = (
            f"Please send the login credentials, invite link, or license key to deliver to the customer:\n\n"
        )

    text = (
        f"{ce(CustomEmojis.KEY, '🔑')} <b>FULFILL MANUAL ORDER #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{qty_prompt}"
        f"<i>(The bot will format this into a copyable block and notify the user immediately):</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("adm_pending_orders"))

@router.message(AdminManualOrderStates.waiting_for_fulfillment_content)
async def msg_admin_man_ful_content(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    content = message.text.strip()
    data = await state.get_data()
    order_id = data.get("order_id")
    await state.clear()

    order, user = await fulfill_manual_order(session, order_id, content)
    if not order:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Order could not be fulfilled or is no longer pending.")
        return

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Order #{order.id} Dispatched & Fulfilled!</b>\n\n"
        f"Credentials have been automatically delivered to {user.full_name if user else 'customer'} on Telegram.",
        reply_markup=get_admin_cancel_keyboard("adm_pending_orders")
    )

    # Notify Customer with delivery receipt
    variant = order.variant
    product = await get_product(session, variant.product_id) if variant else None
    prod_title = product.title if product else "Digital Service"
    qty = getattr(order, "quantity", 1) or 1
    qty_badge = f"\n{ce(CustomEmojis.SPARKLE, '🔢')} <b>Quantity:</b> <b>{qty} unit(s)</b>" if qty > 1 else ""

    customer_msg = (
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>YOUR ORDER #{order.id} HAS BEEN DISPATCHED!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_title}\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> {variant.name if variant else 'Plan'}{qty_badge}\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>YOUR DELIVERED CREDENTIALS / INVITE LINK:</b>\n\n"
        f"<pre><code>{order.delivered_content}</code></pre>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Your subscription is under 100% replacement warranty! Saved permanently in Order History.</i>"
    )
    from keyboards.user_keyboards import get_post_delivery_keyboard
    cust_kb = get_post_delivery_keyboard(order.id)
    try:
        await bot.send_message(order.user_id, customer_msg, reply_markup=cust_kb)
    except Exception:
        pass

    # Group/Channel Notification (only if not already broadcast)
    if not getattr(order, "broadcast_sent", False):
        from utils.notifications import send_order_notification
        try:
            user_obj = await get_user(session, order.user_id)
            buyer_name = user_obj.full_name if user_obj else "Customer"
            remaining = await get_available_stock_count(session, variant.id) if variant else 0
            bot_me = getattr(bot, '_cached_me', None) or await bot.get_me()
            await send_order_notification(
                bot=bot,
                order_id=order.id,
                buyer_name=buyer_name,
                product_title=prod_title,
                variant_name=variant.name if variant else "Plan",
                amount=order.amount,
                stock_left=remaining,
                bot_username=bot_me.username or ""
            )
            order.broadcast_sent = True
            await session.commit()
        except Exception:
            pass

@router.callback_query(F.data.startswith("adm_man_ref_"))
async def cb_admin_man_ref(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    order_id = int(callback.data.split("_")[3])
    order, user = await cancel_and_refund_order(session, order_id)

    if not order:
        await callback.message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Order not found or already processed.")
        return

    await callback.message.edit_text(
        f"{ce(CustomEmojis.LOCK, '❌')} <b>Order #{order.id} Cancelled & Refunded!</b>\n\n"
        f"{config.CURRENCY_SYMBOL}{order.amount:.2f} was returned to {user.full_name if user else 'customer'}'s wallet.",
        reply_markup=get_admin_cancel_keyboard("adm_pending_orders")
    )

    # Notify customer
    try:
        refund_msg = (
            f"{ce(CustomEmojis.FIRE, '🔔')} <b>ORDER #{order.id} CANCELLED & REFUNDED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Your order could not be activated and <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b> has been refunded to your wallet balance.\n\n"
            f"Current Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
            f"Please contact support ({config.SUPPORT_USERNAME}) for details."
        )
        await bot.send_message(order.user_id, refund_msg)
    except Exception:
        pass

# ================= 3. DEPOSIT APPROVALS =================

@router.callback_query(F.data == "adm_deposits")
async def cb_admin_deposits(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    deposits = await get_pending_deposits(session)
    if not deposits:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>No pending deposit requests!</b> All requests are reviewed.",
            reply_markup=get_admin_cancel_keyboard("admin_home")
        )
        return

    text = f"{ce(CustomEmojis.WALLET, '💳')} <b>PENDING DEPOSIT REQUESTS ({len(deposits)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    await callback.message.edit_text(text)

    for dep in deposits[:5]:
        dep_text = (
            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit #{dep.id}</b>\n"
            f"{ce(CustomEmojis.VERIFIED, '👤')} User: <code>{dep.user_id}</code>\n"
            f"{ce(CustomEmojis.WALLET, '💰')} Amount: <b>{config.CURRENCY_SYMBOL}{dep.amount:.2f}</b>\n"
            f"{ce(CustomEmojis.KEY, '🔢')} UTR: <code>{dep.utr_number or 'Not provided'}</code>\n"
            f"{ce(CustomEmojis.STAR, '📅')} Date: {dep.created_at.strftime('%d/%m %H:%M')}"
        )
        if dep.proof_file_id:
            try:
                await callback.message.answer_photo(
                    photo=dep.proof_file_id,
                    caption=dep_text,
                    reply_markup=get_deposit_approval_keyboard(dep.id)
                )
                continue
            except Exception:
                pass
        await callback.message.answer(dep_text, reply_markup=get_deposit_approval_keyboard(dep.id))

@router.callback_query(F.data.startswith("adm_dep_appr_"))
async def cb_admin_dep_approve(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    deposit_id = int(callback.data.split("_")[3])

    deposit, user = await approve_deposit(session, deposit_id)
    if not deposit:
        await callback.message.answer("Deposit already processed or not found.")
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"{ce(CustomEmojis.CHECK, '✅')} Deposit #{deposit.id} APPROVED! Added {config.CURRENCY_SYMBOL}{deposit.amount:.2f} to User <code>{deposit.user_id}</code>.")

    # Check if this deposit was created for a Direct 1-Click Purchase
    if deposit.target_variant_id:
        target_var = await get_variant(session, deposit.target_variant_id)
        if target_var:
            order, err = await fulfill_order(session, user.telegram_id, target_var.id, target_var.price)
            if order and not err:
                prod = await get_product(session, target_var.product_id)
                prod_title = prod.title if prod else "Digital Item"
                cust_deliv_msg = (
                    f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT APPROVED & ORDER #{order.id} DELIVERED!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{prod_title}</b>\n"
                    f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{target_var.name}</b>\n"
                    f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{ce(CustomEmojis.KEY, '🔑')} <b>YOUR DELIVERED ACCOUNT / CODE:</b>\n\n"
                    f"<pre><code>{order.delivered_content}</code></pre>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Your subscription is under 100% replacement warranty! Saved permanently in Order History.</i>"
                )
                from keyboards.user_keyboards import get_post_delivery_keyboard
                cust_kb = get_post_delivery_keyboard(order.id)
                try:
                    await bot.send_message(deposit.user_id, cust_deliv_msg, reply_markup=cust_kb)
                except Exception:
                    pass

                # Group/Channel Notification
                from utils.notifications import send_order_notification
                try:
                    remaining = await get_available_stock_count(session, target_var.id)
                    bot_me = getattr(bot, '_cached_me', None) or await bot.get_me()
                    await send_order_notification(
                        bot=bot,
                        order_id=order.id,
                        buyer_name=user.full_name if user else "Customer",
                        product_title=prod_title,
                        variant_name=target_var.name,
                        amount=order.amount,
                        stock_left=remaining,
                        bot_username=bot_me.username or ""
                    )
                except Exception:
                    pass
                return

    # Normal Deposit notification
    try:
        user_msg = (
            f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>DEPOSIT APPROVED & CREDITED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Receipt ID: #{deposit.id}\n"
            f"Amount Credited: <b>+{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
            f"Current Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
            f"Your funds are ready to use. Tap 'Explore Store' to make a purchase!"
        )
        await bot.send_message(deposit.user_id, user_msg)
    except Exception:
        pass

@router.callback_query(F.data.startswith("adm_dep_rej_"))
async def cb_admin_dep_reject(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    deposit_id = int(callback.data.split("_")[3])

    deposit = await reject_deposit(session, deposit_id)
    if not deposit:
        await callback.message.answer("Deposit already processed or not found.")
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"{ce(CustomEmojis.LOCK, '❌')} Deposit #{deposit.id} has been REJECTED.")

    try:
        user_msg = (
            f"{ce(CustomEmojis.LOCK, '⚠️')} <b>DEPOSIT REJECTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Deposit ID:</b> #{deposit.id}\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount:</b> {config.CURRENCY_SYMBOL}{deposit.amount:.2f}\n\n"
            f"Your deposit could not be verified. Please contact {config.SUPPORT_USERNAME} if you think this is a mistake."
        )
        await bot.send_message(deposit.user_id, user_msg)
    except Exception:
        pass

@router.callback_query(F.data.startswith("adm_dep_detail_"))
async def cb_admin_dep_detail(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    deposit_id = int(callback.data.split("_")[3])
    deposit = await get_deposit(session, deposit_id)
    if not deposit:
        await callback.message.answer("Deposit record not found.")
        return

    user = await get_user(session, deposit.user_id)
    user_name = user.full_name if user else f"User {deposit.user_id}"
    user_handle = f"@{user.username}" if user and user.username else "NoUsername"

    text = (
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>DEPOSIT DETAILS #{deposit.id}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"✦ <b>User:</b> {user_name} ({user_handle})\n"
        f"✦ <b>Telegram ID:</b> <code>{deposit.user_id}</code>\n"
        f"✦ <b>Amount:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
        f"✦ <b>Gateway:</b> <code>{deposit.gateway}</code>\n"
        f"✦ <b>Status:</b> <code>{deposit.status}</code>\n"
        f"✦ <b>UTR / Note:</b> <code>{deposit.utr_number or 'None'}</code>\n"
        f"✦ <b>Date:</b> {deposit.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if deposit.created_at else 'N/A'}\n"
    )
    if deposit.proof_file_id:
        try:
            await callback.message.answer_photo(
                photo=deposit.proof_file_id,
                caption=text,
                reply_markup=get_deposit_approval_keyboard(deposit.id) if deposit.status == "PENDING" else get_admin_cancel_keyboard("adm_deposits")
            )
            return
        except Exception:
            pass

    await callback.message.answer(
        text,
        reply_markup=get_deposit_approval_keyboard(deposit.id) if deposit.status == "PENDING" else get_admin_cancel_keyboard("adm_deposits")
    )

@router.callback_query(F.data.startswith("adm_stock_clear_"))
async def cb_admin_stock_clear(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variant_id = int(callback.data.split("_")[3])
    await delete_unsold_stock_by_variant(session, variant_id)
    await callback.message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} All unsold stock lines for Plan #{variant_id} cleared successfully!"
    )
    callback.data = f"adm_stock_manage_{variant_id}"
    await cb_admin_stock_manage(callback, session)

# ================= 4. INVENTORY & STOCK MANAGEMENT =================

@router.callback_query(F.data == "adm_stock")
async def cb_admin_stock(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variants = await get_all_variants(session)

    if not variants:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.LOCK, '⚠️')} No plans/variants created yet. Create a product and plan first!",
            reply_markup=get_admin_cancel_keyboard("admin_home")
        )
        return

    stock_counts = {}
    for var in variants:
        stock_counts[var.id] = await get_available_stock_count(session, var.id)

    text = (
        f"{ce(CustomEmojis.KEY, '🔑')} <b>INVENTORY & STOCK MANAGEMENT HUB</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Select a subscription plan below to upload stock, view unsold accounts, or clear inventory:\n"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_stock_inventory_keyboard(variants, stock_counts))

@router.callback_query(F.data.startswith("adm_stock_manage_"))
async def cb_admin_stock_manage(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variant_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, variant_id)
    if not variant:
        await callback.message.answer("Plan not found.")
        return

    stock_count = await get_available_stock_count(session, variant_id)
    is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")
    prod_title = variant.product.title if variant.product else "Product"

    text = (
        f"{ce(CustomEmojis.SHOP, '📦')} <b>INVENTORY CONTROLS FOR:</b>\n"
        f"<b>{prod_title} — {variant.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Price:</b> {config.CURRENCY_SYMBOL}{variant.price:.2f}\n"
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>Type:</b> {variant.variant_type}\n"
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Fulfillment Mode:</b> {ce(CustomEmojis.FIRE, '⏱️') + ' Manual Dispatch (1-2h)' if is_manual else ce(CustomEmojis.FIRE, '⚡') + ' Automated Instant Stock'}\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Current Available Stock:</b> <b>{stock_count} items</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_variant_stock_actions_keyboard(variant_id, is_manual, stock_count))

@router.callback_query(F.data.startswith("adm_stock_add_"))
async def cb_admin_stock_add(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variant_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, variant_id)
    current_stock = await get_available_stock_count(session, variant_id)
    prod_title = variant.product.title if variant and variant.product else "Product"

    await state.update_data(variant_id=variant_id)
    await state.set_state(AdminStockStates.waiting_for_stock_lines)

    text = (
        f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>UPLOAD STOCK FOR: {prod_title} — {variant.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Current Live Stock:</b> {current_stock} accounts\n\n"
        f"Paste the accounts or license keys <b>line-by-line (one per line)</b>:\n\n"
        f"<code>email1@netflix.com:Password123 | PIN: 1234 | Screen 1\nemail2@netflix.com:Password456 | PIN: 5678 | Screen 2</code>\n\n"
        f"<i>(Send your lines below to insert them into live inventory):</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("adm_stock"))

@router.message(AdminStockStates.waiting_for_stock_lines, F.text)
async def msg_admin_stock_lines(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    raw_text = message.text.strip()
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    if not lines:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} No valid accounts found. Send at least one line.")
        return

    data = await state.get_data()
    variant_id = data.get("variant_id")
    await state.clear()

    added_count = await add_stock_bulk(session, variant_id, lines)
    total_stock = await get_available_stock_count(session, variant_id)
    variant = await get_variant(session, variant_id)
    prod_title = variant.product.title if variant and variant.product else "Product"

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Successfully Added {added_count} Stock Items!</b>\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_title}\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> {variant.name if variant else ''}\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>New Live Available Stock:</b> <b>{total_stock} items</b>",
        reply_markup=get_admin_cancel_keyboard("adm_stock")
    )

    # Send Restock Alert to Group/Channel
    from utils.notifications import send_restock_alert
    try:
        bot_me = getattr(bot, '_cached_me', None) or await bot.get_me()
        await send_restock_alert(
            bot=bot,
            product_title=prod_title,
            variant_name=variant.name if variant else "",
            added_count=added_count,
            total_stock=total_stock,
            bot_username=bot_me.username or "",
            product_id=variant.product_id if variant else None,
            variant_id=variant_id
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("adm_stock_view_"))
async def cb_admin_stock_view(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variant_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, variant_id)
    unsold = await get_unsold_stock_by_variant(session, variant_id)

    if not unsold:
        await callback.message.answer("No unsold stock available for this plan.", show_alert=True)
        return

    stock_text = f"{ce(CustomEmojis.SEARCH, '👁️')} <b>UNSOLD INVENTORY ({len(unsold)} items):</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for idx, s in enumerate(unsold[:20], 1):
        stock_text += f"{idx}. <code>{s.content}</code>\n"

    if len(unsold) > 20:
        stock_text += f"\n<i>...and {len(unsold) - 20} more items.</i>"

    await callback.message.edit_text(stock_text, reply_markup=get_admin_cancel_keyboard(f"adm_stock_manage_{variant_id}"))

@router.callback_query(F.data.startswith("adm_stock_setslots_"))
async def cb_admin_stock_setslots(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variant_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, variant_id)
    if not variant:
        await callback.message.answer("Plan not found.")
        return
    current_slots = await get_available_stock_count(session, variant_id)
    prod_title = variant.product.title if variant.product else "Product"

    await state.update_data(edit_var_id=variant_id, from_stock_hub=True)
    await state.set_state(AdminVariantEditStates.waiting_for_new_stock_qty)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>SET AVAILABLE SLOTS FOR:</b>\n"
        f"<b>{prod_title} — {variant.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current available slots: <b>{current_slots}</b>\n\n"
        f"How many activation slots/accounts do you have ready right now?\n"
        f"<i>(Send a number below, e.g. <code>10</code>, <code>25</code>, or <code>0</code>):</i>",
        reply_markup=get_admin_cancel_keyboard(f"adm_stock_manage_{variant_id}")
    )

# ================= 5. CATEGORY MANAGEMENT =================

@router.callback_query(F.data == "adm_cats")
async def cb_admin_cats(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    categories = await get_all_categories(session)
    text = (
        f"{ce(CustomEmojis.SHOP, '📁')} <b>CATEGORY MANAGEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Categories: {len(categories)}\n\n"
        f"Click <b>'Delete'</b> to remove a category or <b>'Add New'</b> to create one:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_categories_keyboard(categories))

@router.callback_query(F.data.startswith("adm_cat_edit_"))
async def cb_admin_cat_edit(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    category = await get_category(session, cat_id)
    if not category:
        await callback.message.answer("Category not found.")
        return

    text = (
        f"{ce(CustomEmojis.SHOP, '📁')} <b>EDIT CATEGORY</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.SHOP, '📁')} <b>Current Name:</b> <b>{category.name}</b>\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Category ID:</b> <code>{category.id}</code>\n\n"
        f"<i>What would you like to do?</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_category_edit_keyboard(cat_id))

@router.callback_query(F.data.startswith("adm_catedit_name_"))
async def cb_admin_catedit_name(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    await state.update_data(edit_cat_id=cat_id)
    await state.set_state(AdminCategoryEditStates.waiting_for_new_name)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '✏️')} <b>Edit Category Name & Emojis</b>\n\n"
        "Send the new <b>Category Name</b> (with emojis if you like):\n"
        "e.g. <code>🍿 Streaming Services</code> or <code>🤖 AI Tools</code>",
        reply_markup=get_admin_cancel_keyboard(f"adm_cat_edit_{cat_id}")
    )

@router.message(AdminCategoryEditStates.waiting_for_new_name, F.text)
async def msg_admin_catedit_name(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    cat_id = data.get("edit_cat_id")
    await state.clear()
    if not cat_id:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Session expired. Please select the category to edit again from /admin.")
        return

    html_name = get_message_html_text(message)
    _, fallback_icon, custom_emoji_id = extract_clean_name_and_emoji(message)

    category = await update_category_details(
        session,
        category_id=cat_id,
        name=html_name,
        emoji=fallback_icon or "📁",
        custom_emoji_id=custom_emoji_id
    )
    if category:
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Category Updated Successfully!</b>\n\n"
            f"{ce(CustomEmojis.SHOP, '📁')} <b>New Name:</b> <b>{category.name}</b>",
            reply_markup=get_admin_category_edit_keyboard(category.id)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update category.")

@router.callback_query(F.data.startswith("adm_cat_view_"))
async def cb_admin_cat_view(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    products = await get_products_by_category(session, cat_id)
    category = await get_category(session, cat_id)
    cat_name = category.name if category else "Category"
    text = (
        f"{ce(CustomEmojis.SHOP, '📦')} <b>PRODUCTS IN: {clean_button_text(cat_name)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Products: {len(products)}\n\n"
        f"Click on a product to edit, or <b>'Add Product'</b> below:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_products_keyboard(products, cat_id))

@router.callback_query(F.data.startswith("adm_cat_del_"))
async def cb_admin_cat_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer("Deleting category...", show_alert=False)
    cat_id = int(callback.data.split("_")[3])
    cat = await get_category(session, cat_id)
    cat_name = cat.name if cat else "Category"
    success = await delete_category(session, cat_id)
    categories = await get_all_categories(session)
    if success:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Category '{clean_button_text(cat_name)}' successfully deleted!</b>\n\n"
            f"<i>The category and its products have been removed from your store.</i>",
            reply_markup=get_admin_categories_keyboard(categories)
        )
    else:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Category not found or already deleted.</b>",
            reply_markup=get_admin_categories_keyboard(categories)
        )

@router.callback_query(F.data == "adm_cat_add")
async def cb_admin_cat_add(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminCategoryStates.waiting_for_name)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>Add New Category</b>\n\n"
        "Send the <b>Category Name</b> (with your emoji/icon if you like):\n"
        "e.g. <code>🍿 Streaming Services</code> or <code>👑 VIP Section</code>",
        reply_markup=get_admin_cancel_keyboard("adm_cats")
    )

@router.message(AdminCategoryStates.waiting_for_name, F.text)
async def msg_admin_cat_name(message: types.Message, state: FSMContext, session: AsyncSession):
    html_name = get_message_html_text(message)
    _, fallback_icon, custom_emoji_id = extract_clean_name_and_emoji(message)
    await state.clear()

    category = await create_category(
        session,
        name=html_name,
        emoji=fallback_icon or "📁",
        custom_emoji_id=custom_emoji_id
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕  Add Another Category", callback_data="adm_cat_add")],
        [InlineKeyboardButton(text="📦  View Products in this Category", callback_data=f"adm_selcat_viewprods_{category.id}")],
        [InlineKeyboardButton(text="📁  All Categories", callback_data="adm_cats")],
        [InlineKeyboardButton(text="⚡  Admin Panel Home", callback_data="admin_home")]
    ])

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Category Created Successfully!</b>\n\n"
        f"{ce(CustomEmojis.SHOP, '📁')} <b>Name:</b> <b>{category.name}</b>\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Category ID:</b> <code>{category.id}</code>\n\n"
        f"What would you like to do next?",
        reply_markup=kb
    )

# ================= 6. PRODUCT MANAGEMENT =================

@router.callback_query(F.data == "adm_prods")
async def cb_admin_prods(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    categories = await get_all_categories(session)
    text = (
        f"{ce(CustomEmojis.SHOP, '📦')} <b>PRODUCT MANAGEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Select a category to view or add products to it:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_category_select_keyboard(categories, action="viewprods"))

@router.callback_query(F.data.startswith("adm_selcat_viewprods_"))
async def cb_admin_cat_viewprods(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    products = await get_products_by_category(session, cat_id)
    category = await get_category(session, cat_id)
    cat_name = category.name if category else "Category"

    text = (
        f"{ce(CustomEmojis.SHOP, '📦')} <b>PRODUCTS IN: {clean_button_text(cat_name)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Products: {len(products)}\n\n"
        f"Click on a product to edit, or <b>'Add Product'</b> below:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_products_keyboard(products, cat_id))

@router.callback_query(F.data.startswith("adm_prod_edit_"))
async def cb_admin_prod_edit(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    product = await get_product(session, prod_id)
    if not product:
        await callback.message.answer("Product not found.")
        return

    text = (
        f"{ce(CustomEmojis.SHOP, '📦')} <b>EDIT PRODUCT: {product.title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Title:</b> {product.title}\n"
        f"<b>Description:</b> {product.description or 'None'}\n\n"
        f"Choose what you want to edit:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_product_edit_keyboard(prod_id, product.category_id))

@router.callback_query(F.data.startswith("adm_prodedit_title_"))
async def cb_admin_prodedit_title(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    await state.update_data(edit_prod_id=prod_id)
    await state.set_state(AdminProductEditStates.waiting_for_new_title)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '✏️')} <b>Edit Product Title & Emojis</b>\n\n"
        "Send the new <b>Product Title</b> (with emojis if you like):\n"
        "e.g. <code>Netflix Premium 4K</code> or <code>Prime Video HD</code>",
        reply_markup=get_admin_cancel_keyboard(f"adm_prod_edit_{prod_id}")
    )

@router.message(AdminProductEditStates.waiting_for_new_title, F.text)
async def msg_admin_prodedit_title(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    prod_id = data.get("edit_prod_id")
    await state.clear()
    if not prod_id:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Session expired. Please select the product to edit again from /admin.")
        return

    html_title = get_message_html_text(message)
    _, fallback_icon, custom_emoji_id = extract_clean_name_and_emoji(message)

    product = await update_product_details(
        session,
        product_id=prod_id,
        title=html_title,
        emoji=fallback_icon or "📦",
        custom_emoji_id=custom_emoji_id
    )
    if product:
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Product Title Updated!</b>\n\n"
            f"{ce(CustomEmojis.SHOP, '📦')} <b>New Title:</b> <b>{product.title}</b>",
            reply_markup=get_admin_product_edit_keyboard(product.id, product.category_id)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update product.")

@router.callback_query(F.data.startswith("adm_prodedit_desc_"))
async def cb_admin_prodedit_desc(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    await state.update_data(edit_prod_id=prod_id)
    await state.set_state(AdminProductEditStates.waiting_for_new_desc)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '📝')} <b>Edit Product Description</b>\n\n"
        "Send the new short description for this product (or send <code>skip</code> to clear):",
        reply_markup=get_admin_cancel_keyboard(f"adm_prod_edit_{prod_id}")
    )

@router.message(AdminProductEditStates.waiting_for_new_desc, F.text)
async def msg_admin_prodedit_desc(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    prod_id = data.get("edit_prod_id")
    await state.clear()
    if not prod_id:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Session expired. Please select the product to edit again from /admin.")
        return

    html_desc = get_message_html_text(message)
    if message.text.strip().lower() == "skip":
        html_desc = None

    product = await update_product_details(
        session,
        product_id=prod_id,
        description=html_desc
    )
    if product:
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Product Description Updated!</b>\n\n"
            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{product.title}</b>",
            reply_markup=get_admin_product_edit_keyboard(product.id, product.category_id)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update product.")

@router.callback_query(F.data.startswith("adm_prod_view_"))
async def cb_admin_prod_view(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    variants = await get_variants_by_product(session, prod_id)
    product = await get_product(session, prod_id)
    prod_title = product.title if product else "Product"
    text = (
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>PLANS FOR: {clean_button_text(prod_title)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Plans: {len(variants)}\n\n"
        f"Click <b>'Delete'</b> or <b>'Add Plan'</b>:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_variants_keyboard(variants, prod_id))

@router.callback_query(F.data.startswith("adm_prod_del_"))
async def cb_admin_prod_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer("Deleting product...", show_alert=False)
    prod_id = int(callback.data.split("_")[3])
    product = await get_product(session, prod_id)
    prod_title = product.title if product else "Product"
    cat_id = product.category_id if product else 1
    success = await delete_product(session, prod_id)

    products = await get_products_by_category(session, cat_id)
    if success:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Product '{clean_button_text(prod_title)}' successfully deleted!</b>\n\n"
            f"<i>The product and all associated plans have been removed.</i>",
            reply_markup=get_admin_products_keyboard(products, cat_id)
        )
    else:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Product not found or already deleted.</b>",
            reply_markup=get_admin_products_keyboard(products, cat_id)
        )

@router.callback_query(F.data.startswith("adm_prod_add_"))
async def cb_admin_prod_add(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    await state.update_data(cat_id=cat_id)
    await state.set_state(AdminProductStates.waiting_for_title)

    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>Add New Product</b>\n\n"
        "Send the <b>Product Title</b> (with emoji if you like, e.g. <code>🍿 Netflix Premium 4K</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_selcat_viewprods_{cat_id}")
    )

@router.message(AdminProductStates.waiting_for_title, F.text)
async def msg_admin_prod_title(message: types.Message, state: FSMContext):
    html_title = get_message_html_text(message)
    _, fallback_icon, custom_emoji_id = extract_clean_name_and_emoji(message)
    await state.update_data(
        title=html_title,
        emoji=fallback_icon or "📦",
        custom_emoji_id=custom_emoji_id
    )
    await state.set_state(AdminProductStates.waiting_for_desc)
    await message.answer(
        f"{ce(CustomEmojis.SHOP, '📦')} Product: <b>{html_title}</b>\n\n"
        f"Now send a <b>Short Description</b> for this product (or send <code>skip</code>):"
    )

@router.message(AdminProductStates.waiting_for_desc, F.text)
async def msg_admin_prod_desc(message: types.Message, state: FSMContext, session: AsyncSession):
    html_desc = get_message_html_text(message)
    if message.text.strip().lower() == "skip":
        html_desc = None

    data = await state.get_data()
    cat_id = data.get("cat_id")
    title = data.get("title")
    emoji = data.get("emoji")
    custom_emoji_id = data.get("custom_emoji_id")
    await state.clear()

    product = await create_product(
        session,
        category_id=cat_id,
        title=title,
        emoji=emoji,
        description=html_desc,
        custom_emoji_id=custom_emoji_id
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕  Add Plans to this Product", callback_data=f"adm_var_add_{product.id}")],
        [InlineKeyboardButton(text="➕  Add Another Product", callback_data=f"adm_prod_add_{cat_id}")],
        [InlineKeyboardButton(text="📦  View Products in Category", callback_data=f"adm_selcat_viewprods_{cat_id}")],
        [InlineKeyboardButton(text="⚡  Admin Panel Home", callback_data="admin_home")]
    ])

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Product Created Successfully!</b>\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Title:</b> <b>{product.title}</b>\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Product ID:</b> <code>{product.id}</code>\n\n"
        f"What would you like to do next?",
        reply_markup=kb
    )

# ================= 7. PLAN / VARIANT MANAGEMENT =================

@router.callback_query(F.data == "adm_variants")
async def cb_admin_variants(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    products = await get_all_products(session)
    text = (
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>MANAGE PLANS & PRICING</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Select a product to view or add subscription plans:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_product_select_keyboard(products, action="viewvars"))

@router.callback_query(F.data.startswith("adm_selprod_viewvars_"))
async def cb_admin_prod_viewvars(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    product = await get_product(session, prod_id)
    variants = await get_variants_by_product(session, prod_id)

    text = (
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>PLANS FOR: {product.emoji} {product.title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Plans: {len(variants)}\n\n"
        f"Click <b>'Delete'</b> or <b>'Add Plan'</b>:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_variants_keyboard(variants, prod_id))

@router.callback_query(F.data.startswith("adm_var_edit_"))
async def cb_admin_var_edit(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, var_id)
    if not variant:
        await callback.message.answer("Plan not found.")
        return

    is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")
    mode_str = "⏱️ MANUAL (Dispatch by Admin)" if is_manual else "⚡ AUTOMATIC (Instant Auto-Stock)"
    dispatch_str = variant.manual_dispatch_time or "1–2 Hours"
    prompt_str = variant.input_prompt or "Default (Asks Email / Phone)"

    lines = [
        f"{ce(CustomEmojis.SPARKLE, '✏️')} <b>EDIT SUBSCRIPTION PLAN</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{variant.product.title if variant.product else 'Digital Item'}</b>",
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan Name:</b> <b>{variant.name}</b>",
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Current Price:</b> <code>{config.CURRENCY_SYMBOL}{variant.price:.2f}</code>",
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>Plan Type:</b> <code>{variant.variant_type}</code>",
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Fulfillment Mode:</b> <b>{mode_str}</b>"
    ]
    if is_manual:
        stock_qty = variant.stock_quantity if getattr(variant, "stock_quantity", None) is not None else 50
        lines.append(f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Dispatch Time:</b> <code>{dispatch_str}</code>")
        lines.append(f"👉 <b>Customer Prompt:</b> <i>{prompt_str}</i>")
        lines.append(f"{ce(CustomEmojis.TROPHY, '📊')} <b>Available Slots / Stock:</b> <b>{stock_qty} slots</b>")

    lines.append(f"{ce(CustomEmojis.SPARKLE, '📝')} <b>Description:</b> <i>{variant.detailed_description or 'Default template'}</i>\n")
    lines.append("What would you like to edit?")

    text = "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_variant_edit_keyboard(
            var_id,
            variant.product_id,
            is_manual=is_manual,
            requires_customer_input=getattr(variant, "requires_customer_input", True)
        )
    )

@router.callback_query(F.data.startswith("adm_varedit_toggleinput_"))
async def cb_admin_varedit_toggleinput(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, var_id)
    if not variant:
        return
    new_input_val = not getattr(variant, "requires_customer_input", True)
    variant = await update_variant_details(session, var_id, requires_customer_input=new_input_val)
    
    is_manual = (variant.fulfillment_type == "MANUAL")
    mode_str = "⏱️ MANUAL (Dispatch by Admin)" if is_manual else "⚡ AUTOMATIC (Instant Auto-Stock)"
    dispatch_str = variant.manual_dispatch_time or "1–2 Hours"
    prompt_str = variant.input_prompt or "Default (Asks Email / Phone)"
    input_req_str = "YES (Bot asks customer for details)" if variant.requires_customer_input else "NO (Direct Admin Delivery — instant receipt to customer)"

    lines = [
        f"{ce(CustomEmojis.SPARKLE, '✏️')} <b>EDIT SUBSCRIPTION PLAN</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{variant.product.title if variant.product else 'Digital Item'}</b>",
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan Name:</b> <b>{variant.name}</b>",
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Current Price:</b> <code>{config.CURRENCY_SYMBOL}{variant.price:.2f}</code>",
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>Plan Type:</b> <code>{variant.variant_type}</code>",
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Fulfillment Mode:</b> <b>{mode_str}</b>"
    ]
    if is_manual:
        stock_qty = variant.stock_quantity if getattr(variant, "stock_quantity", None) is not None else 50
        lines.append(f"⚙️ <b>Customer Input:</b> <b>{input_req_str}</b>")
        lines.append(f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Dispatch Time:</b> <code>{dispatch_str}</code>")
        if variant.requires_customer_input:
            lines.append(f"👉 <b>Customer Prompt:</b> <i>{prompt_str}</i>")
        lines.append(f"{ce(CustomEmojis.TROPHY, '📊')} <b>Available Slots / Stock:</b> <b>{stock_qty} slots</b>")

    lines.append(f"{ce(CustomEmojis.SPARKLE, '📝')} <b>Description:</b> <i>{variant.detailed_description or 'Default template'}</i>\n")
    lines.append("What would you like to edit?")

    text = "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_variant_edit_keyboard(
            var_id,
            variant.product_id,
            is_manual=is_manual,
            requires_customer_input=getattr(variant, "requires_customer_input", True)
        )
    )

@router.callback_query(F.data.startswith("adm_varedit_togglemode_"))
async def cb_admin_varedit_togglemode(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, var_id)
    if not variant:
        return
    new_mode = "MANUAL" if variant.fulfillment_type != "MANUAL" else "AUTOMATIC"
    variant = await update_variant_details(session, var_id, fulfillment_type=new_mode)
    
    is_manual = (variant.fulfillment_type == "MANUAL")
    mode_str = "⏱️ MANUAL (Dispatch by Admin)" if is_manual else "⚡ AUTOMATIC (Instant Auto-Stock)"
    dispatch_str = variant.manual_dispatch_time or "1–2 Hours"
    prompt_str = variant.input_prompt or "Default (Asks Email / Phone)"
    input_req_str = "YES (Bot asks customer for details)" if getattr(variant, "requires_customer_input", True) else "NO (Direct Admin Delivery — instant receipt)"

    lines = [
        f"{ce(CustomEmojis.SPARKLE, '✏️')} <b>EDIT SUBSCRIPTION PLAN</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{variant.product.title if variant.product else 'Digital Item'}</b>",
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan Name:</b> <b>{variant.name}</b>",
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Current Price:</b> <code>{config.CURRENCY_SYMBOL}{variant.price:.2f}</code>",
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>Plan Type:</b> <code>{variant.variant_type}</code>",
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Fulfillment Mode:</b> <b>{mode_str}</b>"
    ]
    if is_manual:
        stock_qty = variant.stock_quantity if getattr(variant, "stock_quantity", None) is not None else 50
        lines.append(f"⚙️ <b>Customer Input:</b> <b>{input_req_str}</b>")
        lines.append(f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Dispatch Time:</b> <code>{dispatch_str}</code>")
        if getattr(variant, "requires_customer_input", True):
            lines.append(f"👉 <b>Customer Prompt:</b> <i>{prompt_str}</i>")
        lines.append(f"{ce(CustomEmojis.TROPHY, '📊')} <b>Available Slots / Stock:</b> <b>{stock_qty} slots</b>")

    lines.append(f"{ce(CustomEmojis.SPARKLE, '📝')} <b>Description:</b> <i>{variant.detailed_description or 'Default template'}</i>\n")
    lines.append("What would you like to edit?")

    text = "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_variant_edit_keyboard(
            var_id,
            variant.product_id,
            is_manual=is_manual,
            requires_customer_input=getattr(variant, "requires_customer_input", True)
        )
    )

@router.callback_query(F.data.startswith("adm_varedit_dispatch_"))
async def cb_admin_varedit_dispatch(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    await state.update_data(edit_var_id=var_id)
    await state.set_state(AdminVariantEditStates.waiting_for_new_dispatch_time)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Edit Expected Dispatch Time</b>\n\n"
        "Send the dispatch timeframe shown to customers (e.g. <code>1–2 Hours</code>, <code>30 Mins</code>, <code>10 Mins</code>, <code>Instant</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_var_edit_{var_id}")
    )

@router.message(AdminVariantEditStates.waiting_for_new_dispatch_time, F.text)
async def msg_admin_varedit_dispatch(message: types.Message, state: FSMContext, session: AsyncSession):
    new_dispatch = message.text.strip()
    data = await state.get_data()
    var_id = data.get("edit_var_id")
    await state.clear()

    variant = await update_variant_details(session, var_id, manual_dispatch_time=new_dispatch)
    if variant:
        is_manual = (variant.fulfillment_type == "MANUAL")
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Dispatch Time Updated!</b>\n\n"
            f"{ce(CustomEmojis.FIRE, '⏱️')} <b>New Dispatch Time:</b> <code>{variant.manual_dispatch_time}</code>",
            reply_markup=get_admin_variant_edit_keyboard(variant.id, variant.product_id, is_manual=is_manual)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update plan.")

@router.callback_query(F.data.startswith("adm_varedit_prompt_"))
async def cb_admin_varedit_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    await state.update_data(edit_var_id=var_id)
    await state.set_state(AdminVariantEditStates.waiting_for_new_input_prompt)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>Edit Customer Input Prompt</b>\n\n"
        "Send the question/prompt asked to the customer before payment (e.g. <code>Please send your Gmail address:</code> or <code>Please send your Jio mobile number:</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_var_edit_{var_id}")
    )

@router.message(AdminVariantEditStates.waiting_for_new_input_prompt, F.text)
async def msg_admin_varedit_prompt(message: types.Message, state: FSMContext, session: AsyncSession):
    new_prompt = get_message_html_text(message)
    if message.text.strip().lower() == "skip":
        new_prompt = None
    data = await state.get_data()
    var_id = data.get("edit_var_id")
    await state.clear()

    variant = await update_variant_details(session, var_id, input_prompt=new_prompt)
    if variant:
        is_manual = (variant.fulfillment_type == "MANUAL")
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Customer Prompt Updated!</b>\n\n"
            f"👉 <b>Prompt:</b> <i>{variant.input_prompt or 'Default'}</i>",
            reply_markup=get_admin_variant_edit_keyboard(variant.id, variant.product_id, is_manual=is_manual)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update plan.")

@router.callback_query(F.data.startswith("adm_varedit_stockqty_"))
async def cb_admin_varedit_stockqty(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    await state.update_data(edit_var_id=var_id)
    await state.set_state(AdminVariantEditStates.waiting_for_new_stock_qty)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Edit Available Activation Stock / Slots</b>\n\n"
        "How many manual activations/orders are currently available for this plan?\n\n"
        "Send the number of available slots (e.g. <code>50</code>, <code>20</code>, <code>10</code> — or send <code>0</code> if out of stock):",
        reply_markup=get_admin_cancel_keyboard(f"adm_var_edit_{var_id}")
    )

@router.message(AdminVariantEditStates.waiting_for_new_stock_qty, F.text)
async def msg_admin_varedit_stockqty(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    try:
        new_qty = int(message.text.strip())
        if new_qty < 0:
            new_qty = 0
    except ValueError:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Invalid number. Send a valid whole number (e.g. <code>50</code> or <code>0</code>):")
        return

    data = await state.get_data()
    var_id = data.get("edit_var_id")
    from_stock_hub = data.get("from_stock_hub", False)
    await state.clear()
    if not var_id:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Session expired. Please select the plan to edit again from /admin.")
        return

    variant = await update_variant_details(session, var_id, stock_quantity=new_qty)
    if variant:
        is_manual = (variant.fulfillment_type == "MANUAL")
        prod_title = variant.product.title if variant.product else "Product"

        if from_stock_hub:
            reply_kb = get_admin_variant_stock_actions_keyboard(variant.id, is_manual=is_manual, stock_count=variant.stock_quantity or 0)
        else:
            reply_kb = get_admin_variant_edit_keyboard(variant.id, variant.product_id, is_manual=is_manual)

        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Available Slots / Stock Updated!</b>\n\n"
            f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_title}\n"
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> {variant.name}\n"
            f"{ce(CustomEmojis.TROPHY, '📊')} <b>Current Available Stock:</b> <code>{variant.stock_quantity} slots</code>"
            + (f"\n\n📣 <i>Restock alert posted to your sales group!</i>" if new_qty > 0 else ""),
            reply_markup=reply_kb
        )

        # Broadcast Restock Alert to Sales Group
        if new_qty > 0:
            from utils.notifications import send_restock_alert
            try:
                bot_me = getattr(bot, '_cached_me', None) or await bot.get_me()
                await send_restock_alert(
                    bot=bot,
                    product_title=prod_title,
                    variant_name=variant.name,
                    added_count=new_qty,
                    total_stock=variant.stock_quantity,
                    bot_username=bot_me.username or "",
                    product_id=variant.product_id,
                    variant_id=variant.id
                )
            except Exception as e:
                logger.warning(f"Restock alert to group failed: {e}")
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update plan.")

@router.callback_query(F.data.startswith("adm_varedit_name_"))
async def cb_admin_varedit_name(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    await state.update_data(edit_var_id=var_id)
    await state.set_state(AdminVariantEditStates.waiting_for_new_name)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '✏️')} <b>Edit Plan Name</b>\n\n"
        "Send the new <b>Plan Name</b> (e.g. <code>1 Month Private Profile</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_var_edit_{var_id}")
    )

@router.message(AdminVariantEditStates.waiting_for_new_name, F.text)
async def msg_admin_varedit_name(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    var_id = data.get("edit_var_id")
    await state.clear()
    if not var_id:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Session expired. Please select the plan to edit again from /admin.")
        return
    
    new_name = get_message_html_text(message)
    variant = await update_variant_details(session, var_id, name=new_name)
    if variant:
        is_manual = (variant.fulfillment_type == "MANUAL")
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Plan Name Updated!</b>\n\n"
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>New Name:</b> <b>{variant.name}</b>\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>Price:</b> <code>{config.CURRENCY_SYMBOL}{variant.price:.2f}</code>",
            reply_markup=get_admin_variant_edit_keyboard(variant.id, variant.product_id, is_manual=is_manual)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update plan.")

@router.callback_query(F.data.startswith("adm_varedit_price_"))
async def cb_admin_varedit_price(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    await state.update_data(edit_var_id=var_id)
    await state.set_state(AdminVariantEditStates.waiting_for_new_price)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Edit Plan Price</b>\n\n"
        "Send the new <b>Price in INR</b> (e.g. <code>149.0</code> or <code>199</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_var_edit_{var_id}")
    )

@router.message(AdminVariantEditStates.waiting_for_new_price, F.text)
async def msg_admin_varedit_price(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        new_price = float(message.text.strip().replace("₹", "").replace("$", ""))
    except ValueError:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Invalid price format. Send a valid number (e.g. <code>149.0</code>):")
        return

    data = await state.get_data()
    var_id = data.get("edit_var_id")
    await state.clear()
    if not var_id:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Session expired. Please select the plan to edit again from /admin.")
        return

    variant = await update_variant_details(session, var_id, price=new_price)
    if variant:
        is_manual = (variant.fulfillment_type == "MANUAL")
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Plan Price Updated!</b>\n\n"
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>New Price:</b> <code>{config.CURRENCY_SYMBOL}{variant.price:.2f}</code>",
            reply_markup=get_admin_variant_edit_keyboard(variant.id, variant.product_id, is_manual=is_manual)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update plan.")

@router.callback_query(F.data.startswith("adm_varedit_desc_"))
async def cb_admin_varedit_desc(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    await state.update_data(edit_var_id=var_id)
    await state.set_state(AdminVariantEditStates.waiting_for_new_desc)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '📝')} <b>Edit Plan Description Card</b>\n\n"
        "Send the new detailed specifications and warranty details (supports HTML & emojis — or send <code>skip</code> for default):",
        reply_markup=get_admin_cancel_keyboard(f"adm_var_edit_{var_id}")
    )

@router.message(AdminVariantEditStates.waiting_for_new_desc, F.text)
async def msg_admin_varedit_desc(message: types.Message, state: FSMContext, session: AsyncSession):
    new_desc = get_message_html_text(message)
    if message.text.strip().lower() == "skip":
        new_desc = None

    data = await state.get_data()
    var_id = data.get("edit_var_id")
    await state.clear()
    if not var_id:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Session expired. Please select the plan to edit again from /admin.")
        return

    variant = await update_variant_details(session, var_id, detailed_description=new_desc)
    if variant:
        is_manual = (variant.fulfillment_type == "MANUAL")
        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Plan Description Updated!</b>\n\n"
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
            f"{ce(CustomEmojis.WALLET, '💰')} <b>Price:</b> <code>{config.CURRENCY_SYMBOL}{variant.price:.2f}</code>",
            reply_markup=get_admin_variant_edit_keyboard(variant.id, variant.product_id, is_manual=is_manual)
        )
    else:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Failed to update plan.")

@router.callback_query(F.data.startswith("adm_var_view_"))
async def cb_admin_var_view(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, var_id)
    if not variant:
        return
    prod_title = variant.product.title if variant.product else "Product"
    is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")
    stock_count = await get_available_stock_count(session, var_id)

    if is_manual:
        mode_text = f"⏱️ <b>Manual Activation</b> (Dispatched by Admin within {variant.manual_dispatch_time})"
        stock_text = "<i>(Manual plans don't require pre-uploaded stock)</i>"
    else:
        mode_text = "⚡ <b>Automated Instant Stock</b>"
        stock_text = f"📊 <b>Current Available Stock:</b> <b>{stock_count} items</b>"

    text = (
        f"{ce(CustomEmojis.SHOP, '📦')} <b>INVENTORY CONTROLS FOR:</b>\n"
        f"<b>{clean_button_text(prod_title)} — {clean_button_text(variant.name)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Price:</b> {config.CURRENCY_SYMBOL}{variant.price:.2f}\n"
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>Type:</b> {variant.variant_type}\n"
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Fulfillment:</b> {mode_text}\n"
        f"{stock_text}\n"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_variant_stock_actions_keyboard(var_id, is_manual, stock_count))

@router.callback_query(F.data.startswith("adm_var_del_"))
async def cb_admin_var_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer("Deleting plan...", show_alert=False)
    var_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, var_id)
    var_name = variant.name if variant else "Plan"
    prod_id = variant.product_id if variant else 1
    success = await delete_variant(session, var_id)

    variants = await get_variants_by_product(session, prod_id)
    if success:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Plan '{clean_button_text(var_name)}' successfully deleted!</b>\n\n"
            f"<i>The plan and its unsold stock have been removed.</i>",
            reply_markup=get_admin_variants_keyboard(variants, prod_id)
        )
    else:
        await callback.message.edit_text(
            f"{ce(CustomEmojis.LOCK, '⚠️')} <b>Plan not found or already deleted.</b>",
            reply_markup=get_admin_variants_keyboard(variants, prod_id)
        )

@router.callback_query(F.data.startswith("adm_var_add_"))
async def cb_admin_var_add(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    await state.update_data(prod_id=prod_id)
    await state.set_state(AdminVariantStates.waiting_for_name)

    await callback.message.edit_text(
        f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>Add New Plan / Duration</b>\n\n"
        "Send the <b>Plan Name</b> (e.g. <code>1 Month Private Profile</code> or <code>1 Year Team Invite</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_selprod_viewvars_{prod_id}")
    )

@router.message(AdminVariantStates.waiting_for_name, F.text)
async def msg_admin_var_name(message: types.Message, state: FSMContext):
    name = get_message_html_text(message)
    await state.update_data(name=name)
    await state.set_state(AdminVariantStates.waiting_for_price)
    await message.answer(f"Plan Name: <b>{name}</b>\n\nNow send the <b>Price</b> in INR (e.g. <code>129.0</code>):")

@router.message(AdminVariantStates.waiting_for_price, F.text)
async def msg_admin_var_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace("₹", "").replace("$", ""))
    except ValueError:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Invalid price format. Please enter a number (e.g. <code>129.0</code>):")
        return

    await state.update_data(price=price)
    await state.set_state(AdminVariantStates.waiting_for_type)
    await message.answer("Now send the <b>Variant Type</b> (e.g. <code>Private Profile</code>, <code>Shared Profile</code>, <code>Invite Link</code>):")

@router.message(AdminVariantStates.waiting_for_type, F.text)
async def msg_admin_var_type(message: types.Message, state: FSMContext):
    variant_type = get_message_html_text(message)
    await state.update_data(variant_type=variant_type)
    await state.set_state(AdminVariantStates.waiting_for_detailed_desc)
    await message.answer(
        f"{ce(CustomEmojis.SPARKLE, '📝')} <b>Detailed Description Card</b> (Shown to customer before buying):\n\n"
        "Send the detailed specifications, features, warranty, and rules:\n\n"
        "<i>(Supports Telegram Premium emojis and HTML tags — or send <code>skip</code> to use the default format.)</i>"
    )

@router.message(AdminVariantStates.waiting_for_detailed_desc, F.text)
async def msg_admin_var_desc(message: types.Message, state: FSMContext):
    detailed_desc = get_message_html_text(message)
    if message.text.strip().lower() == "skip":
        detailed_desc = None

    await state.update_data(detailed_description=detailed_desc)
    await state.set_state(AdminVariantStates.waiting_for_fulfillment_type)

    data = await state.get_data()
    prod_id = data.get("prod_id")

    text = (
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Choose Fulfillment Delivery Mode</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"How should this subscription plan be delivered to customers?\n\n"
        f"⚡ <b>100% Automated Instant Stock:</b>\n"
        f"Bot automatically draws from uploaded accounts/keys and delivers within 1 second after payment.\n\n"
        f"⏱️ <b>Manual Activation (Ask Email / Phone):</b>\n"
        f"Bot asks customer for their Gmail/Phone number (e.g. YouTube family invite / Hotstar activation), creates a pending order, and you fulfill it manually."
    )
    await message.answer(text, reply_markup=get_admin_fulfillment_type_keyboard(f"adm_selprod_viewvars_{prod_id}"))

@router.callback_query(AdminVariantStates.waiting_for_fulfillment_type, F.data == "adm_var_ff_AUTOMATIC")
async def cb_admin_var_ff_auto(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    data = await state.get_data()
    prod_id = data.get("prod_id")
    name = data.get("name")
    price = data.get("price")
    variant_type = data.get("variant_type")
    detailed_desc = data.get("detailed_description")
    await state.clear()

    variant = await create_variant(
        session,
        product_id=prod_id,
        name=name,
        price=price,
        variant_type=variant_type,
        detailed_description=detailed_desc,
        fulfillment_type="AUTOMATIC"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Upload Stock to this Plan", callback_data=f"adm_stock_add_{variant.id}")],
        [InlineKeyboardButton(text="➕ Add Another Plan", callback_data=f"adm_var_add_{prod_id}")],
        [InlineKeyboardButton(text="🏷️ View All Plans for this Product", callback_data=f"adm_selprod_viewvars_{prod_id}")],
        [InlineKeyboardButton(text="⚡ Admin Panel Home", callback_data="admin_home")]
    ])

    await callback.message.edit_text(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Automated Plan Created Successfully!</b>\n\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Price:</b> <b>{config.CURRENCY_SYMBOL}{variant.price:.2f}</b>\n"
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Mode:</b> ⚡ Automated Instant Stock\n\n"
        f"What would you like to do next?",
        reply_markup=kb
    )

@router.callback_query(AdminVariantStates.waiting_for_fulfillment_type, F.data.in_(["adm_var_ff_MANUAL", "adm_var_ff_MANUAL_INPUT", "adm_var_ff_MANUAL_DIRECT"]))
async def cb_admin_var_ff_manual(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    requires_input = (callback.data != "adm_var_ff_MANUAL_DIRECT")
    await state.update_data(requires_customer_input=requires_input)
    await state.set_state(AdminVariantStates.waiting_for_dispatch_time)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Expected Dispatch Timeframe</b>\n\n"
        f"Send the dispatch time shown to customers (e.g. <code>1–2 Hours</code>, <code>30 Mins</code>, <code>10 Mins</code>, <code>Instant</code>):\n\n"
        f"<i>(Send <code>skip</code> to use default <code>1–2 Hours</code>):</i>"
    )

@router.message(AdminVariantStates.waiting_for_dispatch_time, F.text)
async def msg_admin_var_dispatch(message: types.Message, state: FSMContext, session: AsyncSession):
    dispatch_time = message.text.strip()
    if dispatch_time.lower() == "skip":
        dispatch_time = "1–2 Hours"
    await state.update_data(manual_dispatch_time=dispatch_time)
    
    data = await state.get_data()
    requires_input = data.get("requires_customer_input", True)

    if requires_input:
        await state.set_state(AdminVariantStates.waiting_for_input_prompt)
        await message.answer(
            f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>Customer Details Prompt</b>\n\n"
            f"What should the bot ask the customer before they purchase?\n\n"
            f"<b>Examples:</b>\n"
            f"• <code>Please send your Gmail address for YouTube invite activation:</code>\n"
            f"• <code>Please send your registered Jio mobile number:</code>\n"
            f"• <code>Please send your SonyLIV mobile number for OTP login:</code>\n\n"
            f"<i>(Send your prompt below or send <code>skip</code> for standard prompt):</i>"
        )
    else:
        # Direct Admin Provisioning (e.g. CapCut Pro, Private Accs)
        prod_id = data.get("prod_id")
        name = data.get("name")
        price = data.get("price")
        variant_type = data.get("variant_type")
        detailed_desc = data.get("detailed_description")

        variant = await create_variant(
            session,
            product_id=prod_id,
            name=name,
            price=price,
            variant_type=variant_type,
            detailed_description=detailed_desc,
            fulfillment_type="MANUAL",
            manual_dispatch_time=dispatch_time,
            input_prompt=None,
            requires_customer_input=False
        )

        prod_obj = await get_product(session, prod_id) if prod_id else None
        prod_title = prod_obj.title if prod_obj else name
        await state.set_data({"variant_id": variant.id, "prod_id": prod_id, "variant_name": variant.name, "prod_title": prod_title})
        await state.set_state(AdminVariantStates.waiting_for_stock_qty)

        await message.answer(
            f"{ce(CustomEmojis.CHECK, '✅')} <b>Direct Provisioning Plan Created!</b>\n\n"
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
            f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Dispatch:</b> {dispatch_time}\n"
            f"⚡ <b>Customer Input:</b> None (Direct receipt issued upon payment)\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{ce(CustomEmojis.TROPHY, '📊')} <b>How many slots (capacity) do you have available right now?</b>\n\n"
            f"This number will be shown to customers so they know stock is available.\n"
            f"<i>(e.g. send <code>20</code> or send <code>0</code> if none yet.)</i>",
            reply_markup=get_admin_cancel_keyboard("adm_stock")
        )

@router.message(AdminVariantStates.waiting_for_input_prompt, F.text)
async def msg_admin_var_input_prompt(message: types.Message, state: FSMContext, session: AsyncSession):
    prompt_text = get_message_html_text(message)
    if message.text.strip().lower() == "skip":
        prompt_text = "Please send your registered Email or Mobile Number for manual activation:"

    data = await state.get_data()
    prod_id = data.get("prod_id")
    name = data.get("name")
    price = data.get("price")
    variant_type = data.get("variant_type")
    detailed_desc = data.get("detailed_description")
    dispatch_time = data.get("manual_dispatch_time") or "1–2 Hours"

    variant = await create_variant(
        session,
        product_id=prod_id,
        name=name,
        price=price,
        variant_type=variant_type,
        detailed_description=detailed_desc,
        fulfillment_type="MANUAL",
        manual_dispatch_time=dispatch_time,
        input_prompt=prompt_text,
        requires_customer_input=True
    )

    # Save variant_id and prod_id, then ask for initial stock slot count
    prod_obj = await get_product(session, prod_id) if prod_id else None
    prod_title = prod_obj.title if prod_obj else name
    await state.set_data({"variant_id": variant.id, "prod_id": prod_id, "variant_name": variant.name, "prod_title": prod_title})
    await state.set_state(AdminVariantStates.waiting_for_stock_qty)

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Manual Plan Created!</b>\n\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{variant.name}</b>\n"
        f"{ce(CustomEmojis.FIRE, '⏱️')} <b>Dispatch:</b> {dispatch_time}\n"
        f"👉 <b>Prompt:</b> <i>{variant.input_prompt}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>How many slots (capacity) do you have available right now?</b>\n\n"
        f"This number will be shown to customers so they know stock is available.\n"
        f"<i>(e.g. send <code>10</code> if you have 10 invites ready. Send <code>0</code> if none yet.)</i>",
        reply_markup=get_admin_cancel_keyboard("adm_stock")
    )

@router.message(AdminVariantStates.waiting_for_stock_qty, F.text)
async def msg_admin_var_manual_stock_qty(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    text = message.text.strip()
    try:
        qty = int(text)
        if qty < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            f"{ce(CustomEmojis.LOCK, '⚠️')} Please send a valid number (e.g. <code>10</code> or <code>0</code>):"
        )
        return

    data = await state.get_data()
    variant_id = data.get("variant_id")
    prod_id = data.get("prod_id")
    prod_title = data.get("prod_title", "Product")
    variant_name = data.get("variant_name", "Plan")
    await state.clear()

    # Update the manual variant's stock_quantity field
    variant = await get_variant(session, variant_id)
    if variant:
        variant.stock_quantity = qty
        await session.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Another Plan", callback_data=f"adm_var_add_{prod_id}")],
        [InlineKeyboardButton(text="🏷️ View All Plans for this Product", callback_data=f"adm_selprod_viewvars_{prod_id}")],
        [InlineKeyboardButton(text="⚡ Admin Panel Home", callback_data="admin_home")]
    ])

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Stock set to {qty} slots!</b>\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {prod_title}\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> {variant_name}\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Available Slots:</b> <b>{qty}</b>\n\n"
        + (f"📣 Sending restock alert to your sales group..." if qty > 0 else ""),
        reply_markup=kb
    )

    # Send restock alert to group if qty > 0
    if qty > 0:
        from utils.notifications import send_restock_alert
        try:
            bot_me = getattr(bot, '_cached_me', None) or await bot.get_me()
            await send_restock_alert(
                bot=bot,
                product_title=prod_title,
                variant_name=variant_name,
                added_count=qty,
                total_stock=qty,
                bot_username=bot_me.username or "",
                product_id=prod_id,
                variant_id=variant_id
            )
        except Exception as e:
            logger.warning(f"Restock alert failed: {e}")

# ================= 8. BROADCAST SYSTEM =================

@router.callback_query(F.data == "adm_broadcast")
async def cb_admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminBroadcastStates.waiting_for_content)
    text = (
        f"{ce(CustomEmojis.FIRE, '📢')} <b>BROADCAST ANNOUNCEMENT TO ALL USERS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send the exact message (text, photos, announcements) you want to broadcast to all registered bot users:\n\n"
        f"<i>(Supports HTML formatting and Telegram emojis)</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

@router.message(AdminBroadcastStates.waiting_for_content)
async def msg_admin_broadcast_content(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()
    user_ids = await get_all_user_ids(session)

    sent_count = 0
    fail_count = 0

    progress_msg = await message.answer(f"{ce(CustomEmojis.FIRE, '🚀')} Broadcasting announcement to {len(user_ids)} users...")

    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent_count += 1
        except Exception:
            fail_count += 1

    await progress_msg.edit_text(
        f"{ce(CustomEmojis.FIRE, '📢')} <b>BROADCAST FINISHED!</b>\n\n"
        f"{ce(CustomEmojis.CHECK, '✅')} Successfully Delivered: {sent_count}\n"
        f"{ce(CustomEmojis.LOCK, '❌')} Failed / Blocked: {fail_count}",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

# ================= 9. USER MANAGEMENT =================

# ================= 9. USER & WALLET DIRECTORY HUB =================

async def _render_user_card(target, user: User, session: AsyncSession, alert_text: str = None):
    # Calculate user statistics
    from database.models import Order
    stmt_orders = select(func.count(Order.id)).where(
        Order.user_id == user.telegram_id,
        Order.status.in_(["PAID", "DELIVERED", "PENDING_DISPATCH", "COMPLETED"])
    )
    order_count = (await session.execute(stmt_orders)).scalar() or 0

    stmt_spent = select(func.coalesce(func.sum(Order.amount), 0.0)).where(
        Order.user_id == user.telegram_id,
        Order.status.in_(["PAID", "DELIVERED", "PENDING_DISPATCH", "COMPLETED"])
    )
    total_spent = float((await session.execute(stmt_spent)).scalar() or 0.0)

    reg_date = user.created_at.strftime("%d %b %Y, %H:%M") if user.created_at else "Earlier"
    uname_str = f"@{user.username}" if user.username else "<i>No username</i>"

    card_text = (
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>CUSTOMER PROFILE & WALLET CARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• <b>Customer Name:</b> <b>{user.full_name}</b>\n"
        f"• <b>Username:</b> {uname_str}\n"
        f"• <b>Telegram Numeric ID:</b> <code>{user.telegram_id}</code>\n"
        f"• <b>Joined On:</b> {reg_date}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Current Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n"
        f"{ce(CustomEmojis.ORDERS, '📦')} <b>Lifetime Orders:</b> <b>{order_count}</b>\n"
        f"{ce(CustomEmojis.DIAMOND, '💎')} <b>Total Amount Spent:</b> <b>{config.CURRENCY_SYMBOL}{total_spent:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Select a quick balance adjustment below or enter a custom amount:</i>"
    )

    kb = get_admin_user_card_keyboard(user.telegram_id)
    if isinstance(target, types.CallbackQuery):
        if alert_text:
            await target.answer(alert_text, show_alert=False)
        try:
            await target.message.edit_text(card_text, reply_markup=kb)
        except Exception:
            await target.message.answer(card_text, reply_markup=kb)
    else:
        await target.answer(card_text, reply_markup=kb)

@router.callback_query(F.data == "adm_users")
@router.callback_query(F.data.startswith("adm_users_page_"))
async def cb_admin_users(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await state.clear()
    
    page = 0
    if callback.data.startswith("adm_users_page_"):
        page = int(callback.data.split("_")[3])

    total_users = await get_all_users_count(session)
    users_with_bal = await get_users_with_balance(session, limit=100)
    total_liabilities = await get_total_wallet_liabilities(session)

    text = (
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>CUSTOMER & WALLET DIRECTORY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Total Registered Users:</b> <b>{total_users:,}</b>\n"
        f"💰 <b>Total Store Wallet Balances:</b> <b>{config.CURRENCY_SYMBOL}{total_liabilities:,.2f}</b>\n"
        f"💳 <b>Users With Active Balance:</b> <b>{len(users_with_bal)}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Customers currently holding money in their wallet:</i>"
    )

    kb = get_admin_users_hub_keyboard(users_with_bal, page=page)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "adm_users_recent")
@router.callback_query(F.data.startswith("adm_recent_page_"))
async def cb_admin_users_recent(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    
    page = 0
    if callback.data.startswith("adm_recent_page_"):
        page = int(callback.data.split("_")[3])

    recent_users = await get_recent_users(session, limit=50)
    text = (
        f"{ce(CustomEmojis.VERIFIED, '👥')} <b>RECENTLY REGISTERED USERS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Showing recent customer signups. Tap any user to inspect:</i>"
    )
    kb = get_admin_recent_users_keyboard(recent_users, page=page)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "adm_user_search")
async def cb_admin_user_search_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminUserManagementStates.waiting_for_user_query)
    text = (
        f"{ce(CustomEmojis.SEARCH, '🔍')} <b>SEARCH CUSTOMER DIRECTORY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send the user's <b>Telegram Numeric ID</b> (e.g. <code>6971497666</code>), <b>@username</b>, or <b>Full Name</b>:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("adm_users"))

@router.message(AdminUserManagementStates.waiting_for_user_query)
async def msg_admin_user_query(message: types.Message, state: FSMContext, session: AsyncSession):
    query = message.text.strip()
    users = await search_users(session, query, limit=10)
    
    if not users:
        await message.answer(
            f"{ce(CustomEmojis.LOCK, '⚠️')} No users found matching '<code>{query}</code>'.\n\n"
            f"Please verify the Telegram ID, username, or name and try again.",
            reply_markup=get_admin_cancel_keyboard("adm_users")
        )
        return

    if len(users) == 1:
        await state.clear()
        await _render_user_card(message, users[0], session)
        return

    # Multiple users found, show selection buttons
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for u in users:
        clean_name = (u.full_name or u.username or f"User {u.telegram_id}")[:18]
        btn_text = f"👤 {clean_name} • ₹{u.balance:.0f} • ID:{u.telegram_id}"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"adm_user_card_{u.telegram_id}", icon_custom_emoji_id=CustomEmojis.VERIFIED)
        ])
    buttons.append([
        InlineKeyboardButton(text="Back to Users Hub", callback_data="adm_users", icon_custom_emoji_id=CustomEmojis.VERIFIED)
    ])
    await state.clear()
    await message.answer(
        f"{ce(CustomEmojis.SEARCH, '🔍')} Found <b>{len(users)} users</b> matching '<code>{query}</code>':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.callback_query(F.data.startswith("adm_user_card_"))
async def cb_admin_user_card_view(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await state.clear()
    user_id = int(callback.data.split("_")[3])
    user = await get_user(session, user_id)
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return
    await _render_user_card(callback, user, session)

@router.callback_query(F.data.startswith("adm_user_adj_"))
async def cb_admin_user_quick_adjust(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    if not check_admin(callback.from_user.id):
        return
    parts = callback.data.split("_")
    user_id = int(parts[3])
    delta = float(parts[4])

    user = await update_user_balance(session, user_id, delta)
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return

    sign = "+" if delta > 0 else ""
    alert_text = f"✅ Balance updated: {sign}₹{delta:.0f} (New: ₹{user.balance:.2f})"
    
    # Notify user asynchronously
    try:
        await bot.send_message(
            user_id,
            f"{ce(CustomEmojis.FIRE, '🔔')} <b>WALLET BALANCE ADJUSTED BY ADMIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Change: <b>{sign}{config.CURRENCY_SYMBOL}{delta:.2f}</b>\n"
            f"Current Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>"
        )
    except Exception:
        pass

    await _render_user_card(callback, user, session, alert_text=alert_text)

@router.callback_query(F.data.startswith("adm_user_setzero_"))
async def cb_admin_user_set_zero(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    if not check_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[3])
    user = await get_user(session, user_id)
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return

    curr_bal = user.balance
    if curr_bal <= 0:
        await callback.answer("User balance is already ₹0.00.", show_alert=True)
        return

    user = await update_user_balance(session, user_id, -curr_bal)
    alert_text = f"✅ Reset balance to ₹0.00 (Deducted ₹{curr_bal:.2f})"

    try:
        await bot.send_message(
            user_id,
            f"{ce(CustomEmojis.FIRE, '🔔')} <b>WALLET BALANCE RESET BY ADMIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Current Balance: <b>{config.CURRENCY_SYMBOL}0.00</b>"
        )
    except Exception:
        pass

    await _render_user_card(callback, user, session, alert_text=alert_text)

@router.callback_query(F.data.startswith("adm_user_custom_"))
async def cb_admin_user_custom_prompt(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[3])
    user = await get_user(session, user_id)
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(target_id=user_id)
    await state.set_state(AdminUserManagementStates.waiting_for_amount_adjust)
    
    text = (
        f"{ce(CustomEmojis.WALLET, '💰')} <b>CUSTOM BALANCE ADJUSTMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Customer: <b>{user.full_name}</b> (ID: <code>{user.telegram_id}</code>)\n"
        f"• Current Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
        f"Send the amount change:\n"
        f"• Use <code>+150</code> to add ₹150\n"
        f"• Use <code>-50</code> to deduct ₹50"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard(f"adm_user_card_{user_id}"))

@router.message(AdminUserManagementStates.waiting_for_amount_adjust)
async def msg_admin_user_adjust(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    val_str = message.text.strip().replace("₹", "").replace("$", "")
    try:
        amount_delta = float(val_str)
    except ValueError:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Invalid amount. Send a number like <code>+100</code> or <code>-50</code>.")
        return

    data = await state.get_data()
    target_id = data.get("target_id")
    await state.clear()

    user = await update_user_balance(session, target_id, amount_delta)
    if not user:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} User not found.", reply_markup=get_admin_cancel_keyboard("adm_users"))
        return

    try:
        sign = "+" if amount_delta > 0 else ""
        await bot.send_message(
            target_id,
            f"{ce(CustomEmojis.FIRE, '🔔')} <b>WALLET BALANCE ADJUSTED BY ADMIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Change: <b>{sign}{config.CURRENCY_SYMBOL}{amount_delta:.2f}</b>\n"
            f"Current Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>"
        )
    except Exception:
        pass

    await _render_user_card(message, user, session, alert_text="✅ Balance updated successfully!")

# ================= 10. WIPE / RESET DEMO DATA =================

@router.callback_query(F.data == "adm_reset_confirm")
async def cb_admin_reset_confirm(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    text = (
        f"{ce(CustomEmojis.LOCK, '⚠️')} <b>WIPE ALL DEMO / SAMPLE DATA?</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"This will delete all sample categories, products, and fake stocks from the database so you can start with a <b>100% clean, fresh store</b>.\n\n"
        f"<i>Are you sure you want to proceed?</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ YES, WIPE ALL DEMO DATA", callback_data="adm_reset_execute")],
        [InlineKeyboardButton(text="❌ Cancel & Go Back", callback_data="admin_home")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "adm_reset_execute")
async def cb_admin_reset_execute(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    from database.crud import clear_all_catalog_data
    await clear_all_catalog_data(session)

    text = (
        f"{ce(CustomEmojis.CHECK, '✅')} <b>DATABASE CATALOG WIPED CLEAN!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"All demo products and fake stocks have been removed.\n\n"
        f"Now you can go to <b>Manage Categories</b> and <b>Manage Products</b> to create your own real products and real stock!"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

# ================= 11. PAYMENT & STORE SETTINGS =================

@router.callback_query(F.data == "adm_settings")
async def cb_admin_settings(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    text = (
        f"{ce(CustomEmojis.CARD, '⚙️')} <b>PAYMENT & STORE CONFIGURATION</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.CARD, '📱')} <b>Current UPI ID:</b> <code>{config.UPI_ID}</code>\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Current Payee Name:</b> <code>{config.UPI_NAME}</code>\n"
        f"{ce(CustomEmojis.SUPPORT, '🛟')} <b>Support Username:</b> <code>{config.SUPPORT_USERNAME}</code>\n"
        f"{ce(CustomEmojis.WALLET, '🪙')} <b>Currency:</b> <code>{config.CURRENCY_SYMBOL}</code>"
        f"</blockquote>\n\n"
        f"<i>Tap below to update your payment details directly in real-time:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_settings_keyboard())

@router.callback_query(F.data == "adm_set_upi_id")
async def cb_admin_set_upi_id(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_upi_id)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.CARD, '📱')} <b>Change UPI ID</b>\n\n"
        f"Current UPI ID: <code>{config.UPI_ID}</code>\n\n"
        "Send your new UPI ID (e.g. <code>9876543210@paytm</code> or <code>samstore@oksbi</code>):",
        reply_markup=get_admin_cancel_keyboard("adm_settings")
    )

@router.message(AdminSettingsStates.waiting_for_upi_id, F.text)
async def msg_admin_set_upi_id(message: types.Message, state: FSMContext):
    new_upi = message.text.strip()
    if "@" not in new_upi:
        await message.answer(f"{ce(CustomEmojis.LOCK, '⚠️')} Please provide a valid UPI ID with '@' (e.g. <code>samstore@oksbi</code>):")
        return

    config.UPI_ID = new_upi
    await state.clear()
    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>UPI ID Updated Successfully!</b>\n\n"
        f"{ce(CustomEmojis.CARD, '📱')} New UPI ID: <code>{config.UPI_ID}</code>\n\n"
        f"<i>All newly generated QR codes will now receive payments to this UPI ID!</i>",
        reply_markup=get_admin_settings_keyboard()
    )

@router.callback_query(F.data == "adm_set_upi_name")
async def cb_admin_set_upi_name(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_upi_name)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Change Payee Name</b>\n\n"
        f"Current Name: <code>{config.UPI_NAME}</code>\n\n"
        "Send the new Payee Name to display on UPI apps:",
        reply_markup=get_admin_cancel_keyboard("adm_settings")
    )

@router.message(AdminSettingsStates.waiting_for_upi_name, F.text)
async def msg_admin_set_upi_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    config.UPI_NAME = new_name
    await state.clear()
    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Payee Name Updated!</b>\n\n"
        f"{ce(CustomEmojis.VERIFIED, '👤')} New Name: <code>{config.UPI_NAME}</code>",
        reply_markup=get_admin_settings_keyboard()
    )

@router.callback_query(F.data == "adm_set_support")
async def cb_admin_set_support(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_support_user)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.SUPPORT, '🛟')} <b>Change Support Username</b>\n\n"
        f"Current Support: <code>{config.SUPPORT_USERNAME}</code>\n\n"
        "Send the Telegram username for customer support (e.g. <code>@SamStoreSupport</code>):",
        reply_markup=get_admin_cancel_keyboard("adm_settings")
    )

@router.message(AdminSettingsStates.waiting_for_support_user, F.text)
async def msg_admin_set_support(message: types.Message, state: FSMContext):
    new_support = message.text.strip()
    if not new_support.startswith("@"):
        new_support = f"@{new_support}"
    config.SUPPORT_USERNAME = new_support
    await state.clear()
    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Support Handle Updated!</b>\n\n"
        f"{ce(CustomEmojis.SUPPORT, '🛟')} New Support: <code>{config.SUPPORT_USERNAME}</code>",
        reply_markup=get_admin_settings_keyboard()
    )

# ================= 12. AUTOMATED GATEWAY CONFIGURATION =================

@router.callback_query(F.data == "adm_gateways")
async def cb_admin_gateways(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    from payments.manager import payment_manager
    is_rzp = payment_manager.razorpay.is_configured
    is_pp = payment_manager.paypal.is_configured
    is_oxa = payment_manager.oxapay.is_configured

    text = (
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>AUTOMATED PAYMENT GATEWAY HUB</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"✦ <b>Razorpay (UPI / INR):</b> {'🟢 Configured & Active' if is_rzp else '⚪ Not Configured'}\n"
        f"✦ <b>PayPal (USD / Cards):</b> {'🟢 Configured & Active' if is_pp else '⚪ Not Configured'}\n"
        f"✦ <b>OxaPay (Crypto / USDT):</b> {'🟢 Configured & Active' if is_oxa else '⚪ Not Configured'}"
        f"</blockquote>\n\n"
        f"<b>How Automated Gateways Work:</b>\n"
        f"1. Customer taps 'PURCHASE NOW'.\n"
        f"2. Chooses UPI (Razorpay), PayPal, or Crypto (OxaPay).\n"
        f"3. <b>Bot auto-verifies payment via Webhook/API and delivers product to chat in 1 second with ZERO manual clicks!</b>\n\n"
        f"<i>Select a gateway below to configure or update your credentials:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_gateway_settings_keyboard(is_rzp, is_pp, is_oxa))

@router.callback_query(F.data == "adm_set_rzp")
async def cb_admin_set_rzp(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_razorpay_key_id)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.KEY, '🔑')} <b>CONFIGURE RAZORPAY GATEWAY</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Step 1 of 2:\n"
        f"Please send your <b>Razorpay Key ID</b> (e.g. <code>rzp_live_xxxxxxxxxx</code>):\n\n"
        f"<i>(You can get this from your Razorpay Dashboard ➜ Settings ➜ API Keys)</i>",
        reply_markup=get_admin_cancel_keyboard("adm_gateways")
    )

@router.message(AdminSettingsStates.waiting_for_razorpay_key_id, F.text)
async def msg_admin_rzp_key_id(message: types.Message, state: FSMContext):
    key_id = message.text.strip()
    await state.update_data(rzp_key_id=key_id)
    await state.set_state(AdminSettingsStates.waiting_for_razorpay_key_secret)
    await message.answer(
        f"{ce(CustomEmojis.KEY, '🔑')} <b>Razorpay Key ID Saved:</b> <code>{key_id}</code>\n\n"
        f"Step 2 of 2:\n"
        f"Now send your <b>Razorpay Key Secret</b>:"
    )

@router.message(AdminSettingsStates.waiting_for_razorpay_key_secret, F.text)
async def msg_admin_rzp_key_secret(message: types.Message, state: FSMContext):
    data = await state.get_data()
    key_id = data.get("rzp_key_id")
    key_secret = message.text.strip()
    await state.clear()

    config.RAZORPAY_KEY_ID = key_id
    config.RAZORPAY_KEY_SECRET = key_secret
    import os
    os.environ["RAZORPAY_KEY_ID"] = key_id
    os.environ["RAZORPAY_KEY_SECRET"] = key_secret

    from payments.manager import payment_manager
    payment_manager.razorpay.is_configured = True

    is_rzp = payment_manager.razorpay.is_configured
    is_pp = payment_manager.paypal.is_configured
    is_oxa = payment_manager.oxapay.is_configured

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>RAZORPAY GATEWAY CONFIGURED & ACTIVATED!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Mode:</b> 100% Automated Instant Auto-Delivery\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>Key ID:</b> <code>{key_id}</code>\n\n"
        f"<i>Customers paying in the bot will now receive dynamic instant checkout links with automated delivery!</i>",
        reply_markup=get_admin_gateway_settings_keyboard(is_rzp, is_pp, is_oxa)
    )

@router.callback_query(F.data == "adm_set_paypal")
async def cb_admin_set_paypal(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_paypal_client_id)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.CARD, '🅿️')} <b>CONFIGURE PAYPAL GATEWAY</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Step 1 of 2:\n"
        f"Please send your <b>PayPal Client ID</b>:\n\n"
        f"<i>(From developer.paypal.com ➜ Apps & Credentials ➜ Live App)</i>",
        reply_markup=get_admin_cancel_keyboard("adm_gateways")
    )

@router.message(AdminSettingsStates.waiting_for_paypal_client_id, F.text)
async def msg_admin_paypal_client_id(message: types.Message, state: FSMContext):
    client_id = message.text.strip().strip('"\' ')
    await state.update_data(paypal_client_id=client_id)
    await state.set_state(AdminSettingsStates.waiting_for_paypal_client_secret)
    await message.answer(
        f"{ce(CustomEmojis.KEY, '🔑')} <b>PayPal Client ID Saved!</b>\n\n"
        f"Step 2 of 2:\n"
        f"Now send your <b>PayPal Secret Key / Client Secret</b>:"
    )

@router.message(AdminSettingsStates.waiting_for_paypal_client_secret, F.text)
async def msg_admin_paypal_client_secret(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get("paypal_client_id")
    client_secret = message.text.strip().strip('"\' ')
    await state.clear()

    config.PAYPAL_CLIENT_ID = client_id
    config.PAYPAL_CLIENT_SECRET = client_secret
    import os
    os.environ["PAYPAL_CLIENT_ID"] = client_id
    os.environ["PAYPAL_CLIENT_SECRET"] = client_secret

    from payments.manager import payment_manager
    payment_manager.paypal._cached_token = None

    is_rzp = payment_manager.razorpay.is_configured
    is_pp = payment_manager.paypal.is_configured
    is_oxa = payment_manager.oxapay.is_configured

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>PAYPAL GATEWAY CONFIGURED & ACTIVATED!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Mode:</b> 100% Automated International Checkout\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>Client ID:</b> <code>{client_id[:10]}...</code>\n\n"
        f"<i>Customers can now pay with PayPal, Visa, Mastercard, Amex, and Discover!</i>",
        reply_markup=get_admin_gateway_settings_keyboard(is_rzp, is_pp, is_oxa)
    )

@router.callback_query(F.data == "adm_set_oxapay")
async def cb_admin_set_oxapay(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminSettingsStates.waiting_for_oxapay_merchant_key)
    await callback.message.edit_text(
        f"{ce(CustomEmojis.DIAMOND, '🪙')} <b>CONFIGURE OXAPAY CRYPTO GATEWAY</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Accept payments in <b>USDT (TRC20, BEP20, Polygon), Bitcoin, Ethereum, Solana, TRX</b>, and more with instant auto-delivery!\n\n"
        f"Please send your <b>OxaPay Merchant API Key</b>:\n\n"
        f"<i>(Get this from OxaPay.com ➜ Dashboard ➜ Merchant ➜ API Keys)</i>",
        reply_markup=get_admin_cancel_keyboard("adm_gateways")
    )

@router.message(AdminSettingsStates.waiting_for_oxapay_merchant_key, F.text)
async def msg_admin_oxapay_key(message: types.Message, state: FSMContext):
    merchant_key = message.text.strip().strip('"\' ')
    await state.clear()

    from payments.manager import payment_manager
    is_valid, test_msg = await payment_manager.oxapay.test_credentials(merchant_key)

    config.OXAPAY_MERCHANT_KEY = merchant_key
    import os
    os.environ["OXAPAY_MERCHANT_KEY"] = merchant_key

    is_rzp = payment_manager.razorpay.is_configured
    is_pp = payment_manager.paypal.is_configured
    is_oxa = payment_manager.oxapay.is_configured

    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>OXAPAY CRYPTO GATEWAY CONFIGURED!</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Status:</b> 100% Automated Instant Crypto Delivery\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>Merchant Key:</b> <code>{merchant_key[:8]}...{merchant_key[-4:] if len(merchant_key) > 12 else ''}</code>\n"
        f"{ce(CustomEmojis.DIAMOND, '💎')} <b>Connection:</b> {test_msg}\n\n"
        f"<i>Customers can now select Crypto (USDT, BTC, SOL, TRX) for instant 1-click checkout and wallet deposits!</i>",
        reply_markup=get_admin_gateway_settings_keyboard(is_rzp, is_pp, is_oxa)
    )

# ================= 10. STORE DESIGN & PAGE CUSTOMIZER =================

@router.callback_query(F.data == "adm_customizer")
async def cb_admin_customizer(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()

    text = (
        f"{ce(CustomEmojis.SPARKLE, '🎨')} <b>STORE DESIGN & PAGE CUSTOMIZER</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Customize the headers, message layout, emojis, dividers, and text for every customer screen in real-time.\n\n"
        f"<b>Select a page below to view and edit its template:</b>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_customizer_keyboard())

@router.callback_query(F.data.startswith("adm_tmpl_view_"))
async def cb_admin_tmpl_view(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()

    key = callback.data.replace("adm_tmpl_view_", "")
    meta = TEMPLATE_METADATA.get(key, {"title": key, "desc": "Custom page template", "tags": []})
    current_content = await get_template(session, key)

    tags_str = " ".join([f"<code>{t}</code>" for t in meta.get("tags", [])])
    if not tags_str:
        tags_str = "<i>No dynamic variables required</i>"

    text = (
        f"{ce(CustomEmojis.SPARKLE, '🎨')} <b>{meta.get('title')}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>Description:</b> {meta.get('desc')}\n"
        f"<b>Available Variables:</b> {tags_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>CURRENT LIVE PREVIEW:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{current_content}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Tap below to edit this template or reset to standard default:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_template_edit_keyboard(key))

@router.callback_query(F.data.startswith("adm_tmpl_edit_"))
async def cb_admin_tmpl_edit(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    key = callback.data.replace("adm_tmpl_edit_", "")
    meta = TEMPLATE_METADATA.get(key, {"title": key, "tags": []})
    await state.update_data(editing_template_key=key)
    await state.set_state(AdminTemplateStates.waiting_for_template_content)

    tags_str = "\n".join([f"• <code>{t}</code>" for t in meta.get("tags", [])])

    text = (
        f"{ce(CustomEmojis.SPARKLE, '✍️')} <b>EDITING: {meta.get('title')}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Send your new message below. You can use:\n"
        f"• Telegram Custom Emojis (<code>&lt;tg-emoji&gt;</code>)\n"
        f"• HTML tags: <code>&lt;b&gt;bold&lt;/b&gt;</code>, <code>&lt;i&gt;italic&lt;/i&gt;</code>, <code>&lt;code&gt;code&lt;/code&gt;</code>, <code>&lt;blockquote&gt;quote&lt;/blockquote&gt;</code>\n\n"
        f"<b>Available Variables you can use:</b>\n"
        f"{tags_str}\n\n"
        f"<i>(Send your new template message below now):</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("adm_customizer"))

@router.message(AdminTemplateStates.waiting_for_template_content, F.text)
async def msg_admin_template_content(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key = data.get("editing_template_key")
    if not key:
        await state.clear()
        await message.answer("Editing session expired. Please open the customizer again.")
        return

    new_content = get_message_html_text(message)
    if not new_content.strip():
        await message.answer("Please send non-empty text.")
        return

    await set_template(session, key, new_content)
    await state.clear()

    meta = TEMPLATE_METADATA.get(key, {"title": key})
    await message.answer(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Template Updated Successfully!</b>\n\n"
        f"<b>Section:</b> {meta.get('title')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>NEW LIVE PREVIEW:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{new_content}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>All customers will now see your newly customized design!</i>",
        reply_markup=get_admin_template_edit_keyboard(key)
    )

@router.callback_query(F.data.startswith("adm_tmpl_reset_"))
async def cb_admin_tmpl_reset(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    key = callback.data.replace("adm_tmpl_reset_", "")
    meta = TEMPLATE_METADATA.get(key, {"title": key})
    default_content = await reset_template(session, key)

    await callback.message.edit_text(
        f"{ce(CustomEmojis.CHECK, '✅')} <b>Template Reset to Default!</b>\n\n"
        f"<b>Section:</b> {meta.get('title')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>DEFAULT PREVIEW:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{default_content}",
        reply_markup=get_admin_template_edit_keyboard(key)
    )
