from aiogram import Router, F, types
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_active_categories,
    get_category,
    get_products_by_category,
    get_product,
    get_variants_by_product,
    get_variant,
    get_available_stock_count,
    get_product_total_stock_count
)
from keyboards.user_keyboards import (
    get_categories_keyboard,
    get_products_keyboard,
    get_variants_keyboard,
    get_product_detail_keyboard
)
from utils.emojis import Emojis, UI
import config

router = Router()

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

    text = (
        f"🛍️ <b>PREMIUM DIGITAL STORE CATALOG</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Select a category below to explore subscriptions, accounts, and tools:\n\n"
        f"<blockquote>"
        f"✦ <b>Instant Delivery:</b> Credentials sent in seconds\n"
        f"✦ <b>Verified Accounts:</b> 100% Genuine & safe\n"
        f"✦ <b>Full Warranty:</b> Covered throughout validity"
        f"</blockquote>\n\n"
        f"👇 <i>Choose your desired category:</i>"
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

    text = (
        f"{category.emoji} <b>CATEGORY ➜ {category.name.upper()}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Select an item to view plans, pricing, and live inventory:\n"
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

    text = (
        f"{category.emoji if category else '📁'} <b>CATEGORY ➜ {category.name.upper() if category else 'PRODUCTS'}</b>\n"
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

    text = (
        f"📦 <b>{product.title.upper()}</b>\n"
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

    product = await get_product(session, variant.product_id)
    stock_count = await get_available_stock_count(session, variant.id)
    has_stock = stock_count > 0

    stock_badge = f"🟢 <b>In Stock</b> ({stock_count} Available)" if has_stock else "🔴 <b>Out of Stock</b>"

    text = (
        f"💎 <b>PRODUCT SPECIFICATION & PRICING</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"📦 <b>Product:</b> {product.title if product else 'Product'}\n"
        f"✨ <b>Plan:</b> <code>{variant.name}</code>\n"
        f"🏷️ <b>Type:</b> {variant.variant_type}\n"
        f"💰 <b>Price:</b> <b>{config.CURRENCY_SYMBOL}{variant.price:.2f}</b>\n"
        f"📊 <b>Inventory:</b> {stock_badge}\n"
        f"⚡ <b>Fulfillment:</b> 100% Automated Instant Delivery\n\n"
        f"<blockquote>"
    )

    if variant.detailed_description:
        text += f"{variant.detailed_description}\n"
    else:
        text += (
            f"✦ <b>Quality:</b> Official UHD/HD stream\n"
            f"✦ <b>Access:</b> Instant login credentials\n"
            f"✦ <b>Warranty:</b> Replacement guarantee for active duration\n"
            f"✦ <b>Rules:</b> Use on assigned screen only"
        )

    text += (
        f"</blockquote>\n\n"
        f"🛡️ <i>Click <b>'PURCHASE NOW'</b> to buy instantly using your wallet balance:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_product_detail_keyboard(
            variant_id=variant.id,
            price=variant.price,
            product_id=variant.product_id,
            has_stock=has_stock
        )
    )
