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
from utils.emojis import Emojis
import config

router = Router()

@router.callback_query(F.data == "nav_shop")
async def cb_nav_shop(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()
    categories = await get_active_categories(session)
    
    if not categories:
        await callback.message.edit_text(
            "🛒 <b>Store Catalog</b>\n\n"
            "No categories available right now. Please check back shortly!",
            reply_markup=get_categories_keyboard([])
        )
        return

    text = (
        f"🛒 <b>WELCOME TO {config.UPI_NAME.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Explore our premium digital products & services.\n"
        f"Select a category below to browse available items:\n\n"
        f"💡 <i>Tap any category button below:</i>"
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

    # Collect stock counts for each product
    stock_counts = {}
    for prod in products:
        stock_counts[prod.id] = await get_product_total_stock_count(session, prod.id)

    text = (
        f"📁 <b>CATEGORY: {category.name.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Browse our available subscriptions and products.\n"
        f"Select any item below to view variants, plans, and stock:\n\n"
        f"👇 <i>Choose a product:</i>"
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
        f"📁 <b>CATEGORY: {category.name.upper() if category else 'PRODUCTS'}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Browse our available subscriptions and products.\n"
        f"Select any item below to view variants, plans, and stock:\n\n"
        f"👇 <i>Choose a product:</i>"
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
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    if product.description:
        text += f"<i>{product.description}</i>\n\n"

    text += (
        f"⚡ <b>Select your desired duration or plan type:</b>\n"
        f"<i>(Click on any plan to see full details & specifications before buying)</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_variants_keyboard(variants, product_id, product.category_id)
    )

@router.callback_query(F.data.startswith("var_"))
async def cb_variant_detail(callback: types.CallbackQuery, session: AsyncSession):
    """
    Detailed Product Card Screen (User Requirement):
    Displays the complete description, warranty, delivery mode, price,
    and stock status before asking the user to confirm purchase.
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

    stock_badge = f"🟢 In Stock ({stock_count} Available)" if has_stock else "🔴 Out of Stock"

    # Format the Detailed Product Card
    text = (
        f"💎 <b>PRODUCT SPECIFICATIONS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Item:</b> {product.title if product else 'Product'}\n"
        f"✨ <b>Plan:</b> {variant.name}\n"
        f"🏷️ <b>Type:</b> {variant.variant_type}\n"
        f"💰 <b>Price:</b> <b>{config.CURRENCY_SYMBOL}{variant.price:.2f}</b>\n"
        f"📊 <b>Stock Status:</b> {stock_badge}\n"
        f"⚡ <b>Fulfillment:</b> Instant Auto-Delivery\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if variant.detailed_description:
        text += f"{variant.detailed_description}\n\n"
    else:
        text += (
            f"📝 <b>Plan Details:</b>\n"
            f"✦ Instant credentials sent directly to your Telegram chat.\n"
            f"✦ 100% genuine and verified subscription.\n"
            f"✦ Replacement warranty during the plan validity.\n\n"
        )

    text += (
        f"🛡️ <i>Click <b>'Buy Now'</b> below to purchase instantly using your wallet balance.</i>"
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
