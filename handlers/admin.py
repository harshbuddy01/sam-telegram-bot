from aiogram import Router, F, types, Bot
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
    delete_category,
    get_products_by_category,
    get_all_products,
    get_product,
    create_product,
    delete_product,
    get_variants_by_product,
    get_all_variants,
    get_variant,
    create_variant,
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
    update_user_balance
)
from keyboards.admin_keyboards import (
    get_admin_main_keyboard,
    get_admin_recent_orders_keyboard,
    get_admin_order_audit_keyboard,
    get_admin_categories_keyboard,
    get_admin_category_select_keyboard,
    get_admin_products_keyboard,
    get_admin_product_select_keyboard,
    get_admin_variants_keyboard,
    get_admin_stock_inventory_keyboard,
    get_admin_variant_stock_actions_keyboard,
    get_admin_pending_orders_keyboard,
    get_admin_manual_order_detail_keyboard,
    get_deposit_approval_keyboard,
    get_admin_cancel_keyboard
)
from utils.states import (
    AdminCategoryStates,
    AdminProductStates,
    AdminVariantStates,
    AdminStockStates,
    AdminBroadcastStates,
    AdminUserManagementStates,
    AdminManualOrderStates
)
from utils.emojis import Emojis, UI, format_emoji
import config

router = Router()

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
        f"⚡ <b>ADMINISTRATOR CONTROL PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Select a management hub below to manage your store:"
    )
    await message.answer(text, reply_markup=get_admin_main_keyboard(pending_deps, pending_orders))

@router.message(Command("addstock"))
async def cmd_addstock(message: types.Message, state: FSMContext, session: AsyncSession):
    if not check_admin(message.from_user.id):
        return
    await state.clear()
    variants = await get_all_variants(session)

    if not variants:
        await message.answer("⚠️ No subscription plans found.")
        return

    stock_counts = {}
    for var in variants:
        stock_counts[var.id] = await get_available_stock_count(session, var.id)

    text = (
        f"🔑 <b>SELECT PLAN TO ADD STOCK:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Click on any plan below to paste and upload accounts/keys:\n"
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
        f"⚙️ <b>ADMIN MANAGEMENT PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome, Administrator <b>{callback.from_user.first_name}</b>.\n"
        f"Select a management option below:"
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
        f"📊 <b>LIVE STORE METRICS & ANALYTICS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Total Registered Customers:</b> {total_users}\n"
        f"💰 <b>Gross Sales Revenue:</b> <b>{config.CURRENCY_SYMBOL}{total_sales:.2f}</b>\n"
        f"🧾 <b>All-Time Orders Completed:</b> {total_orders}\n"
        f"📅 <b>Orders Placed Today:</b> {orders_today}\n"
        f"📊 <b>Active Unsold Credentials:</b> {total_stock} in stock\n"
        f"⏳ <b>Pending Manual Orders:</b> {pending_manual}\n"
        f"💳 <b>Pending Deposit Approvals:</b> {pending_deposits}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
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
            f"🧾 <b>ALL ORDERS & SALES AUDIT LOG</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"ℹ️ <i>No customer orders placed yet in the database.</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))
        return

    text = (
        f"🧾 <b>RECENT ORDERS & SALES AUDIT LOG ({len(orders)})</b>\n"
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

    status_badge = "🟢 COMPLETED (DELIVERED)" if order.status == "COMPLETED" else ("⏳ PENDING DISPATCH" if order.status == "PENDING_DISPATCH" else "❌ CANCELLED / REFUNDED")

    text = (
        f"🔍 <b>DATABASE ORDER AUDIT PROOF #{order.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Customer Name:</b> {user.full_name if user else 'Unknown'}\n"
        f"🆔 <b>Telegram ID:</b> <code>{order.user_id}</code>\n"
        f"💬 <b>Username:</b> @{user.username or 'NoUsername' if user else 'None'}\n"
        f"💰 <b>Amount Paid:</b> <b>{config.CURRENCY_SYMBOL}{order.amount:.2f}</b>\n"
        f"📊 <b>Order Status:</b> {status_badge}\n"
        f"📅 <b>Timestamp:</b> {date_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Product:</b> {prod_title}\n"
        f"✨ <b>Plan:</b> <code>{var_name}</code>\n"
        f"📱/📧 <b>Customer Input (Phone/Email):</b>\n"
        f"<code>{order.customer_input or 'None (Auto Stock Plan)'}</code>\n\n"
        f"🔑 <b>DELIVERED CREDENTIALS / CODE:</b>\n"
        f"<pre><code>{order.delivered_content or 'Pending dispatch'}</code></pre>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ <i>Verified Authentic Database Record</i>"
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
            f"⏳ <b>PENDING MANUAL ORDERS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ <i>No pending manual orders right now! All orders have been dispatched.</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))
        return

    text = (
        f"⏳ <b>PENDING MANUAL ORDERS ({len(orders)})</b>\n"
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

    text = (
        f"📋 <b>MANUAL ORDER DETAILS #{order.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Customer:</b> {user.full_name if user else 'User'} (ID: <code>{order.user_id}</code>)\n"
        f"📦 <b>Item:</b> {prod_title} — {var_name}\n"
        f"💰 <b>Amount Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n"
        f"📅 <b>Ordered At:</b> {order.created_at.strftime('%d %b %Y, %H:%M UTC')}\n"
        f"📊 <b>Status:</b> ⏳ PENDING DISPATCH\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 <b>CUSTOMER PROVIDED DETAILS:</b>\n"
        f"<code>{order.customer_input or 'None'}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Click 'Fulfill' to send the login details/link, or 'Cancel & Refund' to refund customer's balance:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_manual_order_detail_keyboard(order.id))

@router.callback_query(F.data.startswith("adm_man_ful_"))
async def cb_admin_man_ful(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    order_id = int(callback.data.split("_")[3])
    await state.set_state(AdminManualOrderStates.waiting_for_fulfillment_content)
    await state.update_data(order_id=order_id)

    text = (
        f"🔑 <b>FULFILL MANUAL ORDER #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Please send the login credentials, invite link, or license key to deliver to the customer:\n\n"
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
        await message.answer("⚠️ Order could not be fulfilled or is no longer pending.")
        return

    await message.answer(
        f"✅ <b>Order #{order.id} Dispatched & Fulfilled!</b>\n\n"
        f"Credentials have been automatically delivered to {user.full_name if user else 'customer'} on Telegram.",
        reply_markup=get_admin_cancel_keyboard("adm_pending_orders")
    )

    # Notify Customer with delivery receipt
    variant = order.variant
    product = await get_product(session, variant.product_id) if variant else None
    prod_title = product.title if product else "Digital Service"

    customer_msg = (
        f"🎉 <b>YOUR ORDER #{order.id} HAS BEEN DISPATCHED!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Product:</b> {prod_title}\n"
        f"✨ <b>Plan:</b> {variant.name if variant else 'Plan'}\n"
        f"💰 <b>Amount Paid:</b> {config.CURRENCY_SYMBOL}{order.amount:.2f}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>YOUR DELIVERED CREDENTIALS / INVITE LINK:</b>\n\n"
        f"<pre><code>{order.delivered_content}</code></pre>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛡️ <i>Your subscription is under 100% replacement warranty! Saved permanently in Order History.</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    cust_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 View in Order History", callback_data="view_orders")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
    ])
    try:
        await bot.send_message(order.user_id, customer_msg, reply_markup=cust_kb)
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
        await callback.message.answer("⚠️ Order not found or already processed.")
        return

    await callback.message.edit_text(
        f"❌ <b>Order #{order.id} Cancelled & Refunded!</b>\n\n"
        f"{config.CURRENCY_SYMBOL}{order.amount:.2f} was returned to {user.full_name if user else 'customer'}'s wallet.",
        reply_markup=get_admin_cancel_keyboard("adm_pending_orders")
    )

    # Notify customer
    try:
        refund_msg = (
            f"🔔 <b>ORDER #{order.id} CANCELLED & REFUNDED</b>\n"
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
            "✅ <b>No pending deposit requests!</b> All requests are reviewed.",
            reply_markup=get_admin_cancel_keyboard("admin_home")
        )
        return

    text = f"💳 <b>PENDING DEPOSIT REQUESTS ({len(deposits)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    await callback.message.edit_text(text)

    for dep in deposits[:5]:
        dep_text = (
            f"🧾 <b>Deposit #{dep.id}</b>\n"
            f"👤 User: <code>{dep.user_id}</code>\n"
            f"💰 Amount: <b>{config.CURRENCY_SYMBOL}{dep.amount:.2f}</b>\n"
            f"🔢 UTR: <code>{dep.utr_number or 'Not provided'}</code>\n"
            f"📅 Date: {dep.created_at.strftime('%d/%m %H:%M')}"
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
    await callback.message.answer(f"✅ Deposit #{deposit.id} APPROVED! Added {config.CURRENCY_SYMBOL}{deposit.amount:.2f} to User <code>{deposit.user_id}</code>.")

    # Notify User
    try:
        user_msg = (
            f"🎉 <b>DEPOSIT APPROVED & CREDITED!</b>\n"
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
    await callback.message.answer(f"❌ Deposit #{deposit.id} has been REJECTED.")

    try:
        user_msg = (
            f"⚠️ <b>DEPOSIT REJECTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
            f"💰 <b>Amount:</b> {config.CURRENCY_SYMBOL}{deposit.amount:.2f}\n\n"
            f"Your deposit could not be verified. Please contact {config.SUPPORT_USERNAME} if you think this is a mistake."
        )
        await bot.send_message(deposit.user_id, user_msg)
    except Exception:
        pass

# ================= 4. INVENTORY & STOCK MANAGEMENT =================

@router.callback_query(F.data == "adm_stock")
async def cb_admin_stock(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variants = await get_all_variants(session)

    if not variants:
        await callback.message.edit_text(
            "⚠️ No plans/variants created yet. Create a product and plan first!",
            reply_markup=get_admin_cancel_keyboard("admin_home")
        )
        return

    stock_counts = {}
    for var in variants:
        stock_counts[var.id] = await get_available_stock_count(session, var.id)

    text = (
        f"🔑 <b>INVENTORY & STOCK MANAGEMENT HUB</b>\n"
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
        f"📦 <b>INVENTORY CONTROLS FOR:</b>\n"
        f"<b>{prod_title} — {variant.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Price:</b> {config.CURRENCY_SYMBOL}{variant.price:.2f}\n"
        f"🏷️ <b>Type:</b> {variant.variant_type}\n"
        f"🚀 <b>Fulfillment Mode:</b> {'⏱️ Manual Dispatch (1-2h)' if is_manual else '⚡ Automated Instant Stock'}\n"
        f"📊 <b>Current Available Stock:</b> <b>{stock_count} items</b>\n\n"
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
        f"✍️ <b>UPLOAD STOCK FOR: {prod_title} — {variant.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Current Live Stock:</b> {current_stock} accounts\n\n"
        f"Paste the accounts or license keys <b>line-by-line (one per line)</b>:\n\n"
        f"<code>email1@netflix.com:Password123 | PIN: 1234 | Screen 1\nemail2@netflix.com:Password456 | PIN: 5678 | Screen 2</code>\n\n"
        f"<i>(Send your lines below to insert them into live inventory):</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("adm_stock"))

@router.message(AdminStockStates.waiting_for_stock_lines)
async def msg_admin_stock_lines(message: types.Message, state: FSMContext, session: AsyncSession):
    raw_text = message.text.strip()
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    if not lines:
        await message.answer("⚠️ No valid accounts found. Send at least one line.")
        return

    data = await state.get_data()
    variant_id = data.get("variant_id")
    await state.clear()

    added_count = await add_stock_bulk(session, variant_id, lines)
    total_stock = await get_available_stock_count(session, variant_id)
    variant = await get_variant(session, variant_id)
    prod_title = variant.product.title if variant and variant.product else "Product"

    await message.answer(
        f"✅ <b>Successfully Added {added_count} Stock Items!</b>\n\n"
        f"📦 <b>Product:</b> {prod_title}\n"
        f"✨ <b>Plan:</b> {variant.name if variant else ''}\n"
        f"📊 <b>New Live Available Stock:</b> <b>{total_stock} items</b>",
        reply_markup=get_admin_cancel_keyboard("adm_stock")
    )

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

    stock_text = f"👁️ <b>UNSOLD INVENTORY ({len(unsold)} items):</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for idx, s in enumerate(unsold[:20], 1):
        stock_text += f"{idx}. <code>{s.content}</code>\n"

    if len(unsold) > 20:
        stock_text += f"\n<i>...and {len(unsold) - 20} more items.</i>"

    await callback.message.edit_text(stock_text, reply_markup=get_admin_cancel_keyboard(f"adm_stock_manage_{variant_id}"))

@router.callback_query(F.data.startswith("adm_stock_clear_"))
async def cb_admin_stock_clear(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    variant_id = int(callback.data.split("_")[3])
    deleted_count = await delete_unsold_stock_by_variant(session, variant_id)

    await callback.message.edit_text(
        f"🗑️ <b>Cleared {deleted_count} unsold stock items</b> from this plan.\n\n"
        f"Stock count is now 0.",
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
        f"📁 <b>CATEGORY MANAGEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Categories: {len(categories)}\n\n"
        f"Click <b>'Delete'</b> to remove a category or <b>'Add New'</b> to create one:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_categories_keyboard(categories))

@router.callback_query(F.data.startswith("adm_cat_del_"))
async def cb_admin_cat_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    await delete_category(session, cat_id)
    categories = await get_all_categories(session)
    await callback.message.edit_text("✅ Category deleted.", reply_markup=get_admin_categories_keyboard(categories))

@router.callback_query(F.data == "adm_cat_add")
async def cb_admin_cat_add(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminCategoryStates.waiting_for_name)
    await callback.message.edit_text(
        "✍️ <b>Add New Category</b>\n\n"
        "Please send the <b>Name</b> for the new category (e.g. <code>Streaming Services</code>):",
        reply_markup=get_admin_cancel_keyboard("adm_cats")
    )

@router.message(AdminCategoryStates.waiting_for_name)
async def msg_admin_cat_name(message: types.Message, state: FSMContext):
    cat_name = message.text.strip()
    await state.update_data(cat_name=cat_name)
    await state.set_state(AdminCategoryStates.waiting_for_emoji)
    await message.answer(
        f"📁 Category Name: <b>{cat_name}</b>\n\n"
        f"Now send an <b>Emoji / Icon</b> for this category (e.g. 🎬 or 🛡️ or 🤖):"
    )

@router.message(AdminCategoryStates.waiting_for_emoji)
async def msg_admin_cat_emoji(message: types.Message, state: FSMContext, session: AsyncSession):
    emoji = message.text.strip()
    data = await state.get_data()
    cat_name = data.get("cat_name")
    await state.clear()

    category = await create_category(session, name=cat_name, emoji=emoji)
    categories = await get_all_categories(session)
    await message.answer(
        f"✅ Category <b>{category.emoji} {category.name}</b> created successfully!",
        reply_markup=get_admin_categories_keyboard(categories)
    )

# ================= 6. PRODUCT MANAGEMENT =================

@router.callback_query(F.data == "adm_prods")
async def cb_admin_prods(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    categories = await get_all_categories(session)
    text = (
        f"📦 <b>PRODUCT MANAGEMENT</b>\n"
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
    category = await get_category(session, cat_id)
    products = await get_products_by_category(session, cat_id)

    text = (
        f"📦 <b>PRODUCTS IN: {category.emoji} {category.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Products: {len(products)}\n\n"
        f"Click <b>'Delete'</b> to remove or <b>'Add'</b> to create a new product:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_products_keyboard(products, cat_id))

@router.callback_query(F.data.startswith("adm_prod_del_"))
async def cb_admin_prod_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    product = await get_product(session, prod_id)
    cat_id = product.category_id if product else 1
    await delete_product(session, prod_id)

    products = await get_products_by_category(session, cat_id)
    await callback.message.edit_text("✅ Product deleted.", reply_markup=get_admin_products_keyboard(products, cat_id))

@router.callback_query(F.data.startswith("adm_prod_add_"))
async def cb_admin_prod_add(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    await state.update_data(cat_id=cat_id)
    await state.set_state(AdminProductStates.waiting_for_title)

    await callback.message.edit_text(
        "✍️ <b>Add New Product</b>\n\n"
        "Send the <b>Product Title</b> (e.g. <code>Netflix Premium 4K</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_selcat_viewprods_{cat_id}")
    )

@router.message(AdminProductStates.waiting_for_title)
async def msg_admin_prod_title(message: types.Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AdminProductStates.waiting_for_emoji)
    await message.answer("Send an <b>Emoji / Icon</b> for this product (e.g. 🍿 or 📦 or 🤖):")

@router.message(AdminProductStates.waiting_for_emoji)
async def msg_admin_prod_emoji(message: types.Message, state: FSMContext):
    emoji = message.text.strip()
    await state.update_data(emoji=emoji)
    await state.set_state(AdminProductStates.waiting_for_desc)
    await message.answer("Send a <b>Short Description</b> for this product (or send <code>skip</code>):")

@router.message(AdminProductStates.waiting_for_desc)
async def msg_admin_prod_desc(message: types.Message, state: FSMContext, session: AsyncSession):
    desc = message.text.strip()
    if desc.lower() == "skip":
        desc = None

    data = await state.get_data()
    cat_id = data.get("cat_id")
    title = data.get("title")
    emoji = data.get("emoji")
    await state.clear()

    product = await create_product(session, category_id=cat_id, title=title, emoji=emoji, description=desc)
    products = await get_products_by_category(session, cat_id)
    await message.answer(
        f"✅ Product <b>{product.emoji} {product.title}</b> created successfully!",
        reply_markup=get_admin_products_keyboard(products, cat_id)
    )

# ================= 7. PLAN / VARIANT MANAGEMENT =================

@router.callback_query(F.data == "adm_variants")
async def cb_admin_variants(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    products = await get_all_products(session)
    text = (
        f"🏷️ <b>MANAGE PLANS & PRICING</b>\n"
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
        f"🏷️ <b>PLANS FOR: {product.emoji} {product.title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Plans: {len(variants)}\n\n"
        f"Click <b>'Delete'</b> or <b>'Add Plan'</b>:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_variants_keyboard(variants, prod_id))

@router.callback_query(F.data.startswith("adm_var_del_"))
async def cb_admin_var_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    variant = await get_variant(session, var_id)
    prod_id = variant.product_id if variant else 1
    await delete_variant(session, var_id)

    variants = await get_variants_by_product(session, prod_id)
    await callback.message.edit_text("✅ Plan deleted.", reply_markup=get_admin_variants_keyboard(variants, prod_id))

@router.callback_query(F.data.startswith("adm_var_add_"))
async def cb_admin_var_add(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    await state.update_data(prod_id=prod_id)
    await state.set_state(AdminVariantStates.waiting_for_name)

    await callback.message.edit_text(
        "✍️ <b>Add New Plan / Duration</b>\n\n"
        "Send the <b>Plan Name</b> (e.g. <code>1 Month Private Profile</code> or <code>1 Year Team Invite</code>):",
        reply_markup=get_admin_cancel_keyboard(f"adm_selprod_viewvars_{prod_id}")
    )

@router.message(AdminVariantStates.waiting_for_name)
async def msg_admin_var_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(AdminVariantStates.waiting_for_price)
    await message.answer(f"Plan Name: <b>{name}</b>\n\nNow send the <b>Price</b> in INR (e.g. <code>129.0</code>):")

@router.message(AdminVariantStates.waiting_for_price)
async def msg_admin_var_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace("₹", "").replace("$", ""))
    except ValueError:
        await message.answer("⚠️ Invalid price format. Please enter a number (e.g. <code>129.0</code>):")
        return

    await state.update_data(price=price)
    await state.set_state(AdminVariantStates.waiting_for_type)
    await message.answer("Now send the <b>Variant Type</b> (e.g. <code>Private Profile</code>, <code>Shared Profile</code>, <code>Invite Link</code>):")

@router.message(AdminVariantStates.waiting_for_type)
async def msg_admin_var_type(message: types.Message, state: FSMContext):
    variant_type = message.text.strip()
    await state.update_data(variant_type=variant_type)
    await state.set_state(AdminVariantStates.waiting_for_detailed_desc)
    await message.answer(
        "📝 <b>Detailed Description Card</b> (Shown to customer before buying):\n\n"
        "Send the detailed specifications, features, warranty, and rules:\n\n"
        "<i>Or send <code>skip</code> to use the default format.</i>"
    )

@router.message(AdminVariantStates.waiting_for_detailed_desc)
async def msg_admin_var_desc(message: types.Message, state: FSMContext, session: AsyncSession):
    detailed_desc = message.text.strip()
    if detailed_desc.lower() == "skip":
        detailed_desc = None

    data = await state.get_data()
    prod_id = data.get("prod_id")
    name = data.get("name")
    price = data.get("price")
    variant_type = data.get("variant_type")
    await state.clear()

    variant = await create_variant(
        session,
        product_id=prod_id,
        name=name,
        price=price,
        variant_type=variant_type,
        detailed_description=detailed_desc
    )
    variants = await get_variants_by_product(session, prod_id)
    await message.answer(
        f"✅ Plan <b>{variant.name}</b> ({config.CURRENCY_SYMBOL}{variant.price}) created successfully!",
        reply_markup=get_admin_variants_keyboard(variants, prod_id)
    )

# ================= 8. BROADCAST SYSTEM =================

@router.callback_query(F.data == "adm_broadcast")
async def cb_admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminBroadcastStates.waiting_for_content)
    text = (
        f"📢 <b>BROADCAST ANNOUNCEMENT TO ALL USERS</b>\n"
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

    progress_msg = await message.answer(f"🚀 Broadcasting announcement to {len(user_ids)} users...")

    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent_count += 1
        except Exception:
            fail_count += 1

    await progress_msg.edit_text(
        f"📢 <b>BROADCAST FINISHED!</b>\n\n"
        f"✅ Successfully Delivered: {sent_count}\n"
        f"❌ Failed / Blocked: {fail_count}",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

# ================= 9. USER MANAGEMENT =================

@router.callback_query(F.data == "adm_users")
async def cb_admin_users(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminUserManagementStates.waiting_for_user_query)
    text = (
        f"👤 <b>USER WALLET ADJUSTMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send the user's <b>Telegram Numeric ID</b> (e.g. <code>6971497666</code>):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

@router.message(AdminUserManagementStates.waiting_for_user_query)
async def msg_admin_user_query(message: types.Message, state: FSMContext, session: AsyncSession):
    query = message.text.strip()
    if not query.isdigit():
        await message.answer("⚠️ Please provide a valid numeric Telegram ID.")
        return

    target_id = int(query)
    user = await get_user(session, target_id)
    if not user:
        await message.answer("⚠️ User not found in database. User must send /start to register.")
        return

    await state.update_data(target_id=target_id)
    await state.set_state(AdminUserManagementStates.waiting_for_amount_adjust)

    text = (
        f"👤 <b>USER FOUND:</b> {user.full_name}\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
        f"💰 Current Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
        f"Send the balance change amount (use <code>+100</code> to add, <code>-50</code> to deduct):"
    )
    await message.answer(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

@router.message(AdminUserManagementStates.waiting_for_amount_adjust)
async def msg_admin_user_adjust(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    val_str = message.text.strip().replace("₹", "").replace("$", "")
    try:
        amount_delta = float(val_str)
    except ValueError:
        await message.answer("⚠️ Invalid amount. Send a number like <code>+100</code> or <code>-50</code>.")
        return

    data = await state.get_data()
    target_id = data.get("target_id")
    await state.clear()

    user = await update_user_balance(session, target_id, amount_delta)

    await message.answer(
        f"✅ <b>Balance Updated!</b>\n\n"
        f"User: {user.full_name}\n"
        f"New Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

    try:
        sign = "+" if amount_delta > 0 else ""
        await bot.send_message(
            target_id,
            f"🔔 <b>WALLET BALANCE ADJUSTED BY ADMIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Change: <b>{sign}{config.CURRENCY_SYMBOL}{amount_delta:.2f}</b>\n"
            f"Current Balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>"
        )
    except Exception:
        pass

# ================= 10. WIPE / RESET DEMO DATA =================

@router.callback_query(F.data == "adm_reset_confirm")
async def cb_admin_reset_confirm(callback: types.CallbackQuery):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    text = (
        f"⚠️ <b>WIPE ALL DEMO / SAMPLE DATA?</b>\n"
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
        f"✅ <b>DATABASE CATALOG WIPED CLEAN!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"All demo products and fake stocks have been removed.\n\n"
        f"Now you can go to <b>Manage Categories</b> and <b>Manage Products</b> to create your own real products and real stock!"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))
