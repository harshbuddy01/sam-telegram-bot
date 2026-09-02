import re
from typing import Optional, List, Dict, Any
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
    get_batch_product_stock_counts,
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
from utils.emojis import Emojis, UI, format_emoji, CustomEmojis, ce, clean_button_text
from utils.templates import render_template
import config

router = Router()

# ================= PRODUCT SEARCH =================

@router.callback_query(F.data == "nav_search")
async def cb_nav_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SearchStates.waiting_for_query)
    text = (
        f"{ce(CustomEmojis.SEARCH, '🔍')} <b>SEARCH SUBSCRIPTION STORE</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Enter any subscription, tool, or keyword to search\n"
        f"<i>(e.g. <code>Netflix</code>, <code>Prime</code>, <code>YouTube</code>, <code>ChatGPT</code>, <code>Canva</code>, <code>VPN</code>)</i>:\n\n"
        f"{ce(CustomEmojis.SPARKLE, '💡')} <i>Or tap below to return to the catalog:</i>"
    )
    await safe_edit_or_reply(callback, text, reply_markup=get_back_button("nav_home"))

@router.message(SearchStates.waiting_for_query)
async def msg_search_query(message: types.Message, state: FSMContext, session: AsyncSession):
    query = message.text.strip()
    await state.clear()

    products = await search_products(session, query)

    if not products:
        text = (
            f"{ce(CustomEmojis.SEARCH, '🔍')} <b>SEARCH RESULTS FOR:</b> <code>{query}</code>\n"
            f"{UI.SECTION_BAR}\n\n"
            f"{ce(CustomEmojis.LOCK, '❌')} <b>No matching subscriptions found for '<code>{query}</code>'</b>\n\n"
            f"<i>Check your spelling or explore all categories from our store catalog!</i>"
        )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Search Another Item", callback_data="nav_search", icon_custom_emoji_id=CustomEmojis.SEARCH)],
            [InlineKeyboardButton(text="Explore Categories", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
            [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
        ])
        await message.answer(text, reply_markup=kb)
        return

    stock_counts = await get_batch_product_stock_counts(session, [p.id for p in products])

    text = (
        f"{ce(CustomEmojis.SEARCH, '🔍')} <b>SEARCH RESULTS ({len(products)} FOUND)</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Matching digital subscriptions for '<b>{query}</b>':\n"
    )
    await message.answer(text, reply_markup=get_search_results_keyboard(products, stock_counts))

async def safe_edit_or_reply(callback: types.CallbackQuery, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        return
    except Exception:
        pass
    
    try:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
        try:
            await callback.message.delete()
        except Exception:
            pass
        return
    except Exception:
        # Fallback to plain text so the message NEVER vanishes
        plain_text = re.sub(r'<[^>]+>', '', text)
        try:
            await callback.message.answer(plain_text, reply_markup=reply_markup, parse_mode=None)
            try:
                await callback.message.delete()
            except Exception:
                pass
        except Exception:
            pass

@router.callback_query(F.data == "nav_shop")
async def cb_nav_shop(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    categories = await get_active_categories(session)
    
    if not categories:
        await safe_edit_or_reply(
            callback,
            f"{ce(CustomEmojis.SHOP, '🛒')} <b>STORE CATALOG</b>\n"
            f"{UI.SECTION_BAR}\n\n"
            "No categories available right now. Please check back shortly!",
            reply_markup=get_categories_keyboard([])
        )
        return

    cat_lines = []
    for cat in categories:
        if "<tg-emoji" in cat.name:
            cat_lines.append(f"{ce(CustomEmojis.SPARKLE, '✨')} <b>{cat.name}</b>")
        else:
            icon = format_emoji(cat.emoji or "📁", cat.custom_emoji_id)
            cat_lines.append(f"{ce(CustomEmojis.SPARKLE, '✨')} {icon} <b>{cat.name}</b>")
    cat_block = "\n".join(cat_lines) if cat_lines else "<i>No categories active yet.</i>"

    text = await render_template(session, "categories_header", store_name=config.STORE_NAME)
    await safe_edit_or_reply(callback, text, reply_markup=get_categories_keyboard(categories))

@router.callback_query(F.data.startswith("cat_"))
async def cb_category_products(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    category_id = int(callback.data.split("_")[1])
    category = await get_category(session, category_id)

    if not category:
        await callback.message.answer("Category not found.")
        return

    products = await get_products_by_category(session, category_id)

    stock_counts = await get_batch_product_stock_counts(session, [p.id for p in products])

    prod_lines = []
    for prod in products:
        stock = stock_counts.get(prod.id, 0)
        stock_str = f"{ce(CustomEmojis.CHECK, '🟢')} {stock} In Stock" if stock > 0 else f"{ce(CustomEmojis.LOCK, '🔴')} Out of Stock"
        clean_prod_title = clean_button_text(prod.title)
        p_icon = format_emoji(prod.emoji or "📦", prod.custom_emoji_id) if "<tg-emoji" not in prod.title else ""
        line = await render_template(
            session,
            "product_item_format",
            prod_icon=p_icon,
            product_title=clean_prod_title,
            stock_badge=stock_str
        )
        prod_lines.append(line)
    prod_block = "\n".join(prod_lines) if prod_lines else "<i>No products available yet.</i>"

    if "<tg-emoji" in category.name:
        cat_header = f"{ce(CustomEmojis.SHOP, '📁')} <b>CATEGORY ➜ {category.name}</b>"
    else:
        cat_emoji = format_emoji(category.emoji, category.custom_emoji_id)
        cat_header = f"{cat_emoji} <b>CATEGORY ➜ {category.name}</b>"

    text = await render_template(
        session,
        "category_products_header",
        cat_header=cat_header,
        category_name=category.name,
        product_list=prod_block
    )

    await safe_edit_or_reply(
        callback,
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

    stock_counts = await get_batch_product_stock_counts(session, [p.id for p in products])

    prod_lines = []
    for prod in products:
        stock = stock_counts.get(prod.id, 0)
        stock_str = f"{ce(CustomEmojis.CHECK, '🟢')} {stock} In Stock" if stock > 0 else f"{ce(CustomEmojis.LOCK, '🔴')} Out of Stock"
        clean_prod_title = clean_button_text(prod.title)
        p_icon = format_emoji(prod.emoji or "📦", prod.custom_emoji_id) if "<tg-emoji" not in prod.title else ""
        line = await render_template(
            session,
            "product_item_format",
            prod_icon=p_icon,
            product_title=clean_prod_title,
            stock_badge=stock_str
        )
        prod_lines.append(line)
    prod_block = "\n".join(prod_lines) if prod_lines else "<i>No products available yet.</i>"

    if category and "<tg-emoji" in category.name:
        cat_header = f"{ce(CustomEmojis.SHOP, '📁')} <b>CATEGORY ➜ {category.name}</b>"
    else:
        cat_emoji = format_emoji(category.emoji, category.custom_emoji_id) if category else "📁"
        cat_header = f"{cat_emoji} <b>CATEGORY ➜ {category.name if category else 'PRODUCTS'}</b>"

    text = await render_template(
        session,
        "category_products_header",
        cat_header=cat_header,
        category_name=category.name if category else "Products",
        product_list=prod_block
    )

    await safe_edit_or_reply(
        callback,
        text,
        reply_markup=get_products_keyboard(products, category_id, stock_counts, page=page)
    )

@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("prod_"))
async def cb_product_variants(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
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

    if variants:
        text += (
            f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Select your plan / duration below:</b>\n"
            f"<i>(Click on any plan to inspect the detailed specs, warranty & delivery info)</i>"
        )
    else:
        text += (
            f"{ce(CustomEmojis.LOCK, '⚠️')} <i>No plans are currently in stock for this item. Please contact support @{config.SUPPORT_USERNAME.lstrip('@')} to order!</i>"
        )

    # Compute USD equivalents for dual pricing display
    usd_prices = {}
    try:
        from payments.manager import payment_manager
        for var in variants:
            _, _, _, usdt_amt = payment_manager.oxapay.calculate_amounts(var.price)
            _, _, _, pp_usd = payment_manager.paypal.calculate_amounts(var.price)
            usd_prices[var.id] = (usdt_amt, pp_usd)
    except Exception:
        pass  # USD prices optional — fallback to INR-only display

    # Clear any previous quantity selection when re-entering product
    await state.update_data(variant_qty={})

    await safe_edit_or_reply(
        callback,
        text,
        reply_markup=get_variants_keyboard(variants, product_id, product.category_id, usd_prices=usd_prices)
    )

@router.callback_query(F.data.startswith("setqty_"))
async def cb_set_quantity(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Inline quantity selector — updates the buy button total and message live."""
    parts = callback.data.split("_")
    variant_id = int(parts[1])
    qty = int(parts[2])

    variant = await get_variant(session, variant_id)
    if not variant:
        await callback.answer("Plan not found.", show_alert=True)
        return

    # Store per-variant qty in FSM
    data = await state.get_data()
    variant_qty = data.get("variant_qty", {})
    variant_qty[str(variant_id)] = qty
    await state.update_data(variant_qty=variant_qty)

    total_val = round(variant.price * qty, 2)
    unit_label = "units" if qty > 1 else "unit"

    # Compute USD equivalents
    try:
        from payments.manager import payment_manager
        _, _, _, total_usdt = payment_manager.oxapay.calculate_amounts(total_val)
        _, _, _, each_usdt = payment_manager.oxapay.calculate_amounts(variant.price)
    except Exception:
        total_usdt = round(total_val / 90.0, 2)
        each_usdt = round(variant.price / 90.0, 2)

    # Show instant toast feedback to user with dual currency
    await callback.answer(f"✅ Selected: {qty} {unit_label} • {config.CURRENCY_SYMBOL}{total_val:.0f} (~${total_usdt:.2f} USDT)", show_alert=False)

    is_manual = (getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL")
    dispatch_time = getattr(variant, "manual_dispatch_time", "1–2 Hours") or "1–2 Hours"

    product = await get_product(session, variant.product_id)
    if product and "<tg-emoji" in product.title:
        prod_display = product.title
    elif product:
        prod_icon = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id)
        prod_display = f"{prod_icon} {product.title}"
    else:
        prod_display = f"{ce(CustomEmojis.SHOP, '📦')} Digital Item"

    stock_count = await get_available_stock_count(session, variant.id)
    has_stock = (stock_count > 0) or is_manual

    if is_manual:
        stock_badge = "Available (1–2h Activation)"
        fulfillment_badge = f"Manual Activation ({dispatch_time})"
        action_note = f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Click <b>'ORDER ACTIVATION'</b> to submit your details &amp; buy:</i>"
    else:
        stock_badge = f"In Stock ({stock_count} Available)" if has_stock else "Out of Stock"
        fulfillment_badge = "100% Instant Delivery"
        action_note = f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Click <b>'PURCHASE NOW'</b> to buy:</i>"

    if variant.detailed_description:
        desc_block = f"<blockquote><b>Features &amp; Specifications:</b>\n{variant.detailed_description.strip()}</blockquote>\n\n"
    else:
        desc_block = ""

    prod_title_clean = product.title if product else "Digital Item"
    prod_icon_clean = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id) if product else "📦"

    from utils.templates import render_template
    text = await render_template(
        session,
        "variant_detail",
        prod_header=f"{ce(CustomEmojis.DIAMOND, '💎')} <b>{prod_display}</b>",
        prod_title=prod_title_clean,
        prod_icon=prod_icon_clean,
        variant_name=variant.name,
        currency=config.CURRENCY_SYMBOL,
        price=f"{variant.price:.0f} · ~${each_usdt:.2f} USDT",
        variant_type=variant.variant_type,
        fulfillment_badge=fulfillment_badge,
        stock_badge=stock_badge,
        description_block=desc_block,
        delivery_time=dispatch_time if is_manual else "Instant (Under 5s)"
    )

    qty_banner = (
        f"<blockquote>"
        f"{ce(CustomEmojis.SPARKLE, '🔢')} <b>Selected Quantity:</b> <b>{qty} {unit_label}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Total Amount:</b> <b>{config.CURRENCY_SYMBOL}{total_val:.2f} · ~${total_usdt:.2f} USDT</b> "
        f"<i>({config.CURRENCY_SYMBOL}{variant.price:.0f} · ~${each_usdt:.2f} each)</i>"
        f"</blockquote>\n"
    )
    text += f"\n{qty_banner}\n{action_note}"

    await safe_edit_or_reply(
        callback,
        text,
        reply_markup=get_product_detail_keyboard(
            variant_id=variant.id,
            price=variant.price,
            product_id=variant.product_id,
            has_stock=has_stock,
            is_manual=is_manual,
            is_admin=config.is_admin(callback.from_user.id),
            quantity=qty,
            usd_price=total_usdt
        )
    )

@router.callback_query(F.data.startswith("var_"))
async def cb_variant_detail(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
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
        prod_display = f"{ce(CustomEmojis.SHOP, '📦')} Digital Item"

    stock_count = await get_available_stock_count(session, variant.id)
    has_stock = (stock_count > 0) or is_manual

    if is_manual:
        stock_badge = "Available (1–2h Activation)"
        fulfillment_badge = f"Manual Activation ({dispatch_time})"
        action_note = f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Click <b>'ORDER ACTIVATION'</b> to submit your details &amp; buy:</i>"
    else:
        stock_badge = f"In Stock ({stock_count} Available)" if has_stock else "Out of Stock"
        fulfillment_badge = "100% Instant Delivery"
        action_note = f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Click <b>'PURCHASE NOW'</b> to buy:</i>"

    if variant.detailed_description:
        desc_clean = variant.detailed_description.strip()
        desc_block = f"<blockquote><b>Features &amp; Specifications:</b>\n{desc_clean}</blockquote>\n\n"
    else:
        desc_block = ""

    prod_title_clean = product.title if product else "Digital Item"
    prod_icon_clean = format_emoji(product.emoji or Emojis.PRODUCT, product.custom_emoji_id) if product else "📦"

    # Read persisted quantity for this variant from FSM
    data = await state.get_data()
    variant_qty = data.get("variant_qty", {})
    qty = int(variant_qty.get(str(variant_id), 1))
    total_val = round(variant.price * qty, 2)
    unit_label = "units" if qty > 1 else "unit"

    # Compute USD equivalents
    try:
        from payments.manager import payment_manager
        _, _, _, total_usdt = payment_manager.oxapay.calculate_amounts(total_val)
        _, _, _, each_usdt = payment_manager.oxapay.calculate_amounts(variant.price)
    except Exception:
        total_usdt = round(total_val / 90.0, 2)
        each_usdt = round(variant.price / 90.0, 2)

    text = await render_template(
        session,
        "variant_detail",
        prod_header=f"{ce(CustomEmojis.DIAMOND, '💎')} <b>{prod_display}</b>",
        prod_title=prod_title_clean,
        prod_icon=prod_icon_clean,
        variant_name=variant.name,
        currency=config.CURRENCY_SYMBOL,
        price=f"{variant.price:.0f} · ~${each_usdt:.2f} USDT",
        variant_type=variant.variant_type,
        fulfillment_badge=fulfillment_badge,
        stock_badge=stock_badge,
        description_block=desc_block,
        delivery_time=dispatch_time if is_manual else "Instant (Under 5s)"
    )

    qty_banner = (
        f"<blockquote>"
        f"{ce(CustomEmojis.SPARKLE, '🔢')} <b>Selected Quantity:</b> <b>{qty} {unit_label}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Total Amount:</b> <b>{config.CURRENCY_SYMBOL}{total_val:.2f} · ~${total_usdt:.2f} USDT</b> "
        f"<i>({config.CURRENCY_SYMBOL}{variant.price:.0f} · ~${each_usdt:.2f} each)</i>"
        f"</blockquote>\n"
    )
    text += f"\n{qty_banner}\n{action_note}"

    await safe_edit_or_reply(
        callback,
        text,
        reply_markup=get_product_detail_keyboard(
            variant_id=variant.id,
            price=variant.price,
            product_id=variant.product_id,
            has_stock=has_stock,
            is_manual=is_manual,
            is_admin=config.is_admin(callback.from_user.id),
            quantity=qty,
            usd_price=total_usdt
        )
    )
