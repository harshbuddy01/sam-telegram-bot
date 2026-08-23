from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from utils.states import SearchStates
from database.crud import (
    get_active_categories,
    get_category,
    get_products_by_category,
    get_product,
    get_variants_by_product,
    get_variant,
    get_available_stock_count,
    get_product_total_stock_count,
    search_products
)
from keyboards.user_keyboards import (
    get_categories_keyboard,
    get_products_keyboard,
    get_variants_keyboard,
    get_product_detail_keyboard,
    get_search_results_keyboard,
    get_back_button
)
from utils.emojis import Emojis, UI, format_emoji, CustomEmojis, ce
import config

router = Router()

# ================= PRODUCT SEARCH =================

@router.callback_query(F.data == "nav_search")
async def cb_nav_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SearchStates.waiting_for_query)
    text = (
        f"🔍 <b>PRODUCT SEARCH</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Please enter the product name or keyword to search (e.g. <code>Netflix</code>, <code>Prime</code>, <code>YouTube</code>, <code>VPN</code>):\n\n"
        f"💡 <i>Or tap below to return to the main menu:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_back_button("nav_home"))

@router.message(SearchStates.waiting_for_query)
async def msg_search_query(message: types.Message, state: FSMContext, session: AsyncSession):
    query = message.text.strip()
    await state.clear()

    products = await search_products(session, query)

    if not products:
        text = (
            f"🔍 <b>SEARCH RESULTS FOR:</b> <code>{query}</code>\n"
            f"{UI.SECTION_BAR}\n\n"
            f"❌ No matching products found for '<b>{query}</b>'.\n\n"
            f"<i>Try searching with a different keyword or browse our full catalog!</i>"
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Search Again", callback_data="nav_search")],
            [InlineKeyboardButton(text="🛍️ Explore Categories", callback_data="nav_shop")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")]
        ])
        await message.answer(text, reply_markup=kb)
        return

    stock_counts = {}
    for prod in products:
        stock_counts[prod.id] = await get_product_total_stock_count(session, prod.id)

    text = (
        f"🔍 <b>SEARCH RESULTS ({len(products)} found)</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Matching subscriptions for '<b>{query}</b>':\n"
    )
    await message.answer(text, reply_markup=get_search_results_keyboard(products, stock_counts))

@router.callback_query(F.data == "nav_shop")
async def cb_nav_shop(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    categories = await get_active_categories(session)
    
    if not categories:
        await callback.message.edit_text(
            "🛒 <b>STORE CATALOG</b>\n"
            f"{UI.SECTION_BAR}\n\n"
            "No categories available right now. Please check back shortly!",
            reply_markup=get_categories_keyboard([])
        )
        return

    cat_lines = []
    for cat in categories:
        if "<tg-emoji" in cat.name:
            cat_lines.append(f"• <b>{cat.name}</b>")
        else:
            icon = format_emoji(cat.emoji or "📁", cat.custom_emoji_id)
            cat_lines.append(f"• {icon} <b>{cat.name}</b>")
    cat_block = "\n".join(cat_lines) if cat_lines else "<i>No categories active yet.</i>"

    text = (
        f"{ce(CustomEmojis.SHOP, '🛍️')} <b>PREMIUM DIGITAL STORE CATALOG</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>Available Categories:</b>\n"
        f"{cat_block}\n\n"
        f"<blockquote>"
        f"✦ <b>Instant Delivery:</b> Credentials sent in seconds\n"
        f"✦ <b>Verified Accounts:</b> 100% Genuine & safe\n"
        f"✦ <b>Full Warranty:</b> Covered throughout validity"
        f"</blockquote>\n\n"
        f"👇 <i>Choose a category below to explore:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_categories_keyboard(categories))

@router.callback_query(F.data.startswith("cat_"))
async def cb_category_products(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    category_id = int(callback.data.split("_")[1])
    category = await get_category(session, category_id)

    if not category:
        await callback.message.answer("Category not found.")
        return

    products = await get_products_by_category(session, category_id)

    stock_counts = {}
    for prod in products:
        stock_counts[prod.id] = await get_product_total_stock_count(session, prod.id)

    prod_lines = []
    for prod in products:
        stock = stock_counts.get(prod.id, 0)
        stock_str = f"🟢 {stock} In Stock" if stock > 0 else "🔴 Out of Stock"
        if "<tg-emoji" in prod.title:
            prod_lines.append(f"• <b>{prod.title}</b> — <i>{stock_str}</i>")
        else:
            p_icon = format_emoji(prod.emoji or "📦", prod.custom_emoji_id)
            prod_lines.append(f"• {p_icon} <b>{prod.title}</b> — <i>{stock_str}</i>")
    prod_block = "\n".join(prod_lines) if prod_lines else "<i>No products available yet.</i>"

    if "<tg-emoji" in category.name:
        cat_header = f"<b>CATEGORY ➜ {category.name}</b>"
    else:
        cat_emoji = format_emoji(category.emoji, category.custom_emoji_id)
        cat_header = f"{cat_emoji} <b>CATEGORY ➜ {category.name.upper()}</b>"

    text = (
        f"{cat_header}\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>Available Products:</b>\n"
        f"{prod_block}\n\n"
        f"👇 <i>Select an item below to view plans and pricing:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_products_keyboard(products, category_id, stock_counts, page=1)
    )

@router.callback_query(F.data.startswith("prodpage_"))
async def cb_products_page(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    _, cat_id_str, page_str = callback.data.split("_")
    category_id = int(cat_id_str)
    page = int(page_str)

    category = await get_category(session, category_id)
    products = await get_products_by_category(session, category_id)

    stock_counts = {}
    for prod in products:
        stock_counts[prod.id] = await get_product_total_stock_count(session, prod.id)

    cat_emoji = format_emoji(category.emoji, category.custom_emoji_id) if category else "📁"
    text = (
        f"{cat_emoji} <b>CATEGORY ➜ {category.name.upper() if category else 'PRODUCTS'}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Select an item to view plans, pricing, and live inventory:\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_products_keyboard(products, category_id, stock_counts, page=page)
    )

@router.callback_query(F.data.startswith("prod_"))
async def cb_product_variants(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    product_id = int(callback.data.split("_")[1])
    product = await get_product(session, product_id)

    if not product:
        await callback.message.answer("Product not found.")
        return

    variants = await get_variants_by_product(session, product_id)
    
    if "<tg-emoji" in product.title:
        title_header = f"<b>{product.title}</b>"
    else:
        icon = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id)
        title_header = f"{icon} <b>{product.title}</b>"

    text = (
        f"{title_header}\n"
        f"{UI.SECTION_BAR}\n\n"
    )
    if product.description:
        text += f"<blockquote>{product.description}</blockquote>\n\n"

    text += (
        f"⚡ <b>Select your plan / duration below:</b>\n"
        f"<i>(Click on any plan to inspect the detailed specs, warranty & delivery info)</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_variants_keyboard(variants, product_id, product.category_id)
    )

@router.callback_query(F.data.startswith("var_"))
async def cb_variant_detail(callback: types.CallbackQuery, session: AsyncSession):
    """
    Detailed Product Card Screen:
    Displays rich specifications, pricing card, warranty, rules, and stock status.
    """
    await callback.answer()
    variant_id = int(callback.data.split("_")[1])
    variant = await get_variant(session, variant_id)

    if not variant:
        await callback.message.answer("Selected plan was not found.")
        return

    is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")
    dispatch_time = getattr(variant, "manual_dispatch_time", "1–2 Hours") or "1–2 Hours"

    product = await get_product(session, variant.product_id)
    if product and "<tg-emoji" in product.title:
        prod_display = product.title
    elif product:
        prod_icon = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id)
        prod_display = f"{prod_icon} {product.title}"
    else:
        prod_display = "📦 Digital Item"

    stock_count = await get_available_stock_count(session, variant.id)
    has_stock = (stock_count > 0) or is_manual

    if is_manual:
        stock_badge = "🟢 <b>Available for Activation</b>"
        fulfillment_badge = f"⏱️ <b>Manual Activation (Dispatched within {dispatch_time})</b>"
        action_note = "🛡️ <i>Click <b>'ORDER ACTIVATION'</b> to submit your details & buy with wallet balance:</i>"
    else:
        stock_badge = f"🟢 <b>In Stock</b> ({stock_count} Available)" if has_stock else "🔴 <b>Out of Stock</b>"
        fulfillment_badge = "⚡ <b>100% Automated Instant Delivery</b>"
        action_note = "🛡️ <i>Click <b>'PURCHASE NOW'</b> to buy instantly using your wallet balance:</i>"

    text = (
        f"💎 <b>PRODUCT SPECIFICATION & PRICING</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"📦 <b>Product:</b> {prod_display}\n"
        f"✨ <b>Plan:</b> <b>{variant.name}</b>\n"
        f"🏷️ <b>Type:</b> {variant.variant_type}\n"
        f"💰 <b>Price:</b> <b>{config.CURRENCY_SYMBOL}{variant.price:.2f}</b>\n"
        f"📊 <b>Status:</b> {stock_badge}\n"
        f"🚀 <b>Fulfillment:</b> {fulfillment_badge}\n\n"
        f"<blockquote>"
    )

    if variant.detailed_description:
        text += f"{variant.detailed_description}\n"
    else:
        cat_name = ""
        if product:
            cat = await get_category(session, product.category_id)
            if cat:
                cat_name = cat.name.upper()
        
        if "OTT" in cat_name or "STREAM" in cat_name:
            quality_text = "Official UHD/HD stream"
        elif "AI" in cat_name:
            quality_text = "Official AI subscription access"
        elif "VPN" in cat_name:
            quality_text = "High-speed secure VPN connection"
        elif "GAM" in cat_name or "UTIL" in cat_name:
            quality_text = "Official premium subscription"
        else:
            quality_text = "Official premium digital subscription"

        text += (
            f"✦ <b>Quality:</b> {quality_text}\n"
            f"✦ <b>Access:</b> Instant login credentials / activation\n"
            f"✦ <b>Warranty:</b> 100% Replacement guarantee during validity\n"
            f"✦ <b>Rules:</b> Use on assigned screen or personal email"
        )

    text += (
        f"</blockquote>\n\n"
        f"{action_note}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_product_detail_keyboard(
            variant_id=variant.id,
            price=variant.price,
            product_id=variant.product_id,
            has_stock=has_stock,
            is_manual=is_manual,
            is_admin=config.is_admin(callback.from_user.id)
        )
    )
