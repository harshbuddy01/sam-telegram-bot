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
    get_user,
    update_user_balance
)
from keyboards.admin_keyboards import (
    get_admin_main_keyboard,
    get_admin_categories_keyboard,
    get_admin_category_select_keyboard,
    get_admin_products_keyboard,
    get_admin_product_select_keyboard,
    get_admin_variants_keyboard,
    get_admin_stock_variant_select_keyboard,
    get_deposit_approval_keyboard,
    get_admin_cancel_keyboard
)
from utils.states import (
    AdminCategoryStates,
    AdminProductStates,
    AdminVariantStates,
    AdminStockStates,
    AdminBroadcastStates,
    AdminUserManagementStates
)
from utils.emojis import Emojis
import config

router = Router()

def check_admin(user_id: int) -> bool:
    return config.is_admin(user_id)

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext, session: AsyncSession):
    if not check_admin(message.from_user.id):
        return
    await state.clear()
    text = (
        f"⚙️ <b>ADMIN MANAGEMENT PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome, Administrator <b>{message.from_user.first_name}</b>.\n"
        f"Select a management category below to configure your store:"
    )
    await message.answer(text, reply_markup=get_admin_main_keyboard())

@router.callback_query(F.data == "admin_home")
async def cb_admin_home(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    text = (
        f"⚙️ <b>ADMIN MANAGEMENT PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome, Administrator <b>{callback.from_user.first_name}</b>.\n"
        f"Select a management option below:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_admin_main_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=get_admin_main_keyboard())

# ================= 1. STORE STATISTICS =================

@router.callback_query(F.data == "adm_stats")
async def cb_admin_stats(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()

    total_users = await get_all_users_count(session)
    total_orders, total_revenue = await get_total_orders_and_revenue(session)
    orders_today = await get_orders_today_count(session)
    active_stock = await get_total_active_stock(session)
    pending_deposits = len(await get_pending_deposits(session))

    text = (
        f"📊 <b>STORE REAL-TIME METRICS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Registered Users:</b> {total_users}\n"
        f"🛍️ <b>Total Orders Completed:</b> {total_orders}\n"
        f"💰 <b>Gross Sales Revenue:</b> {config.CURRENCY_SYMBOL}{total_revenue:.2f}\n"
        f"📈 <b>Orders Placed Today:</b> {orders_today}\n"
        f"📦 <b>Active Stock in Inventory:</b> {active_stock} items\n"
        f"⏳ <b>Pending Deposit Approvals:</b> {pending_deposits}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

# ================= 2. PENDING DEPOSITS =================

@router.callback_query(F.data == "adm_deposits")
async def cb_admin_deposits(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    pending = await get_pending_deposits(session)

    if not pending:
        await callback.message.edit_text(
            "💳 <b>PENDING DEPOSITS</b>\n\n"
            "✅ All deposit requests have been processed. No pending items!",
            reply_markup=get_admin_cancel_keyboard("admin_home")
        )
        return

    text = f"💳 <b>PENDING DEPOSITS ({len(pending)})</b>\n\n"
    for dep in pending:
        text += (
            f"• <b>ID #{dep.id}</b> | User <code>{dep.user_id}</code> | "
            f"<b>{config.CURRENCY_SYMBOL}{dep.amount:.2f}</b> | UTR: <code>{dep.utr_number or 'N/A'}</code>\n"
        )
    text += "\n<i>Approve or Reject individual requests via their alert cards.</i>"

    await callback.message.edit_text(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

@router.callback_query(F.data.startswith("adm_dep_appr_"))
async def cb_admin_approve_deposit(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    deposit_id = int(callback.data.split("_")[3])

    deposit, user = await approve_deposit(session, deposit_id)
    if not deposit:
        await callback.message.answer("Deposit already processed or not found.")
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Deposit #{deposit.id} for {config.CURRENCY_SYMBOL}{deposit.amount:.2f} has been APPROVED.")

    # Notify User
    try:
        user_msg = (
            f"🎉 <b>DEPOSIT APPROVED & CREDITED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧾 <b>Deposit ID:</b> #{deposit.id}\n"
            f"💰 <b>Amount Credited:</b> <b>{config.CURRENCY_SYMBOL}{deposit.amount:.2f}</b>\n"
            f"💳 <b>New Wallet Balance:</b> <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>\n\n"
            f"<i>You can now browse the shop and place orders!</i>"
        )
        await bot.send_message(deposit.user_id, user_msg)
    except Exception:
        pass

@router.callback_query(F.data.startswith("adm_dep_rej_"))
async def cb_admin_reject_deposit(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
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

    # Notify User
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

# ================= 3. CATEGORY MANAGEMENT =================

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

    await create_category(session, name=cat_name, emoji=emoji)
    categories = await get_all_categories(session)
    await message.answer(
        f"✅ Category <b>{emoji} {cat_name}</b> created successfully!",
        reply_markup=get_admin_categories_keyboard(categories)
    )

# ================= 4. PRODUCT MANAGEMENT =================

@router.callback_query(F.data == "adm_prods")
async def cb_admin_prods(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    categories = await get_all_categories(session)
    text = (
        f"📦 <b>PRODUCT MANAGEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Select a category to view or add products:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_category_select_keyboard(categories, action="viewprods"))

@router.callback_query(F.data.startswith("adm_selcat_viewprods_"))
async def cb_admin_view_cat_prods(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    cat_id = int(callback.data.split("_")[3])
    category = await get_category(session, cat_id)
    products = await get_products_by_category(session, cat_id)

    text = (
        f"📦 <b>PRODUCTS IN {category.name.upper() if category else ''}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Products: {len(products)}"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_products_keyboard(products, cat_id))

@router.callback_query(F.data.startswith("adm_prod_del_"))
async def cb_admin_prod_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    prod = await get_product(session, prod_id)
    cat_id = prod.category_id if prod else 0
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
        reply_markup=get_admin_cancel_keyboard("adm_prods")
    )

@router.message(AdminProductStates.waiting_for_title)
async def msg_admin_prod_title(message: types.Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AdminProductStates.waiting_for_emoji)
    await message.answer(f"Product Title: <b>{title}</b>\n\nNow send an emoji/icon (e.g. 🍿 or 📦):")

@router.message(AdminProductStates.waiting_for_emoji)
async def msg_admin_prod_emoji(message: types.Message, state: FSMContext):
    emoji = message.text.strip()
    await state.update_data(emoji=emoji)
    await state.set_state(AdminProductStates.waiting_for_desc)
    await message.answer("Now send a short description for this product (or send <code>skip</code>):")

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
        f"✅ Product <b>{product.title}</b> created successfully!\nNow add plans/variants to it.",
        reply_markup=get_admin_products_keyboard(products, cat_id)
    )

# ================= 5. VARIANTS / PLANS MANAGEMENT =================

@router.callback_query(F.data == "adm_variants")
async def cb_admin_variants(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    products = await get_all_products(session)
    text = (
        f"🏷️ <b>PLAN & VARIANT MANAGEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Select a product to view or add its plans/prices:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_product_select_keyboard(products, action="viewvars"))

@router.callback_query(F.data.startswith("adm_selprod_viewvars_"))
async def cb_admin_view_prod_vars(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    prod_id = int(callback.data.split("_")[3])
    product = await get_product(session, prod_id)
    variants = await get_variants_by_product(session, prod_id)

    text = (
        f"🏷️ <b>PLANS FOR {product.title.upper() if product else ''}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Plans: {len(variants)}"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_variants_keyboard(variants, prod_id))

@router.callback_query(F.data.startswith("adm_var_del_"))
async def cb_admin_var_del(callback: types.CallbackQuery, session: AsyncSession):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    var_id = int(callback.data.split("_")[3])
    var = await get_variant(session, var_id)
    prod_id = var.product_id if var else 0
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
        "✍️ <b>Add New Plan/Variant</b>\n\n"
        "Send the <b>Plan Name</b> (e.g. <code>1 Month Private Profile</code> or <code>12 Months Shared</code>):",
        reply_markup=get_admin_cancel_keyboard("adm_variants")
    )

@router.message(AdminVariantStates.waiting_for_name)
async def msg_admin_var_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(AdminVariantStates.waiting_for_price)
    await message.answer(f"Plan: <b>{name}</b>\n\nNow send the <b>Price</b> in ₹ (e.g. <code>129</code> or <code>359.50</code>):")

@router.message(AdminVariantStates.waiting_for_price)
async def msg_admin_var_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace(config.CURRENCY_SYMBOL, ""))
    except ValueError:
        await message.answer("⚠️ Invalid price. Send a valid number (e.g. 129):")
        return

    await state.update_data(price=price)
    await state.set_state(AdminVariantStates.waiting_for_type)
    await message.answer("Now send the <b>Variant Type</b> (e.g. <code>Private Profile</code>, <code>Shared Profile</code>, <code>Activation Key</code>):")

@router.message(AdminVariantStates.waiting_for_type)
async def msg_admin_var_type(message: types.Message, state: FSMContext):
    variant_type = message.text.strip()
    await state.update_data(variant_type=variant_type)
    await state.set_state(AdminVariantStates.waiting_for_detailed_desc)
    await message.answer(
        "📝 <b>Detailed Description Card</b> (Shown to customer before buying):\n\n"
        "Send the detailed specifications, features, warranty, and rules (supports HTML tags like <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>):\n\n"
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

# ================= 6. BULK STOCK UPLOADER =================

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

    text = (
        f"🔑 <b>BULK STOCK INVENTORY UPLOAD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Select the plan you want to add stock/accounts for:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_stock_variant_select_keyboard(variants))

@router.callback_query(F.data.startswith("adm_stock_select_"))
async def cb_admin_stock_select(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
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
        f"🔑 <b>UPLOAD STOCK FOR: {prod_title} — {variant.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Current Available Stock:</b> {current_stock} items\n\n"
        f"Send the accounts / keys line-by-line (one per line):\n\n"
        f"<code>email1:pass1 | Pin: 1234\nemail2:pass2 | Pin: 5678</code>"
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
        f"📊 <b>New Available Stock:</b> <b>{total_stock} items</b>",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

# ================= 7. BROADCAST SYSTEM =================

@router.callback_query(F.data == "adm_broadcast")
async def cb_admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminBroadcastStates.waiting_for_content)

    await callback.message.edit_text(
        "📢 <b>BROADCAST ANNOUNCEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the message (text, image with caption, etc.) that you want to send to ALL registered bot users:",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

@router.message(AdminBroadcastStates.waiting_for_content)
async def msg_admin_broadcast_content(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()
    user_ids = await get_all_user_ids(session)

    status_msg = await message.answer(f"⏳ Broadcasting message to {len(user_ids)} users...")

    success = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"📢 <b>Broadcast Completed!</b>\n\n"
        f"✅ Successfully Delivered: {success}\n"
        f"❌ Failed / Blocked: {failed}",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

# ================= 8. USER BALANCE MANAGEMENT =================

@router.callback_query(F.data == "adm_users")
async def cb_admin_users(callback: types.CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminUserManagementStates.waiting_for_user_query)

    await callback.message.edit_text(
        "👤 <b>USER BALANCE MANAGEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the <b>Telegram User ID</b> of the customer to view/adjust their wallet balance:",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

@router.message(AdminUserManagementStates.waiting_for_user_query)
async def msg_admin_user_query(message: types.Message, state: FSMContext, session: AsyncSession):
    query = message.text.strip()
    if not query.isdigit():
        await message.answer("⚠️ Please send a valid numeric Telegram ID (e.g. <code>6085016731</code>):")
        return

    user_id = int(query)
    user = await get_user(session, user_id)

    if not user:
        await message.answer("❌ User not found in database. Make sure they have started the bot.")
        return

    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminUserManagementStates.waiting_for_amount_adjust)

    text = (
        f"👤 <b>USER FOUND: {user.full_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"💰 <b>Current Balance:</b> {config.CURRENCY_SYMBOL}{user.balance:.2f}\n"
        f"💳 <b>Total Spent:</b> {config.CURRENCY_SYMBOL}{user.total_spent:.2f}\n\n"
        f"Send the amount to add or subtract (e.g. <code>+100</code> or <code>-50</code>):"
    )
    await message.answer(text, reply_markup=get_admin_cancel_keyboard("admin_home"))

@router.message(AdminUserManagementStates.waiting_for_amount_adjust)
async def msg_admin_balance_adjust(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    raw_amt = message.text.strip().replace(config.CURRENCY_SYMBOL, "")
    try:
        amount_delta = float(raw_amt)
    except ValueError:
        await message.answer("⚠️ Invalid amount. Send e.g. <code>+100</code> or <code>-50</code>:")
        return

    data = await state.get_data()
    target_id = data.get("target_user_id")
    await state.clear()

    user = await update_user_balance(session, target_id, amount_delta)

    await message.answer(
        f"✅ <b>Balance Updated!</b>\n\n"
        f"User <code>{user.telegram_id}</code> new balance: <b>{config.CURRENCY_SYMBOL}{user.balance:.2f}</b>",
        reply_markup=get_admin_cancel_keyboard("admin_home")
    )

    # Notify User
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

# ================= 9. WIPE / RESET DEMO DATA =================

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
