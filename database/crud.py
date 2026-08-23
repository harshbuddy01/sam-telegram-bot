import datetime
from typing import Optional, List, Tuple
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Category, Product, Variant, Stock, Order, Deposit
import config

# ================= USER CRUD =================

async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    full_name: str,
    referrer_id: Optional[int] = None
) -> Tuple[User, bool]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        # Update username or name if changed
        if user.username != username or user.full_name != full_name:
            user.username = username
            user.full_name = full_name
            await session.commit()
        return user, False

    # Prevent self-referral or invalid referrer
    valid_referrer = None
    if referrer_id and referrer_id != telegram_id:
        ref_check = await session.execute(select(User).where(User.telegram_id == referrer_id))
        if ref_check.scalar_one_or_none():
            valid_referrer = referrer_id

    new_user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name or "",
        balance=0.0,
        total_spent=0.0,
        referrer_id=valid_referrer,
        joined_at=datetime.datetime.utcnow()
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user, True

async def get_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def update_user_balance(session: AsyncSession, telegram_id: int, amount_delta: float) -> Optional[User]:
    user = await get_user(session, telegram_id)
    if user:
        user.balance = round(user.balance + amount_delta, 2)
        if amount_delta < 0:
            user.total_spent = round(user.total_spent + abs(amount_delta), 2)
        await session.commit()
        await session.refresh(user)
    return user

async def get_all_users_count(session: AsyncSession) -> int:
    stmt = select(func.count(User.id))
    result = await session.execute(stmt)
    return result.scalar() or 0

async def get_all_user_ids(session: AsyncSession) -> List[int]:
    stmt = select(User.telegram_id).where(User.is_banned == False)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_user_referrals_count(session: AsyncSession, telegram_id: int) -> int:
    stmt = select(func.count(User.id)).where(User.referrer_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar() or 0

# ================= CATEGORY CRUD =================

async def get_active_categories(session: AsyncSession) -> List[Category]:
    stmt = (
        select(Category)
        .join(Product, Category.id == Product.category_id)
        .where(Category.is_active == True, Product.is_active == True)
        .distinct()
        .order_by(Category.sort_order, Category.id)
    )
    result = await session.execute(stmt)
    cats = list(result.scalars().all())
    if not cats:
        stmt_all = select(Category).where(Category.is_active == True).order_by(Category.sort_order, Category.id)
        res_all = await session.execute(stmt_all)
        cats = list(res_all.scalars().all())
    return cats

async def get_all_categories(session: AsyncSession) -> List[Category]:
    stmt = select(Category).order_by(Category.sort_order, Category.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_category(session: AsyncSession, category_id: int) -> Optional[Category]:
    stmt = select(Category).where(Category.id == category_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def create_category(
    session: AsyncSession,
    name: str,
    emoji: str = "📁",
    custom_emoji_id: Optional[str] = None
) -> Category:
    category = Category(name=name, emoji=emoji, custom_emoji_id=custom_emoji_id)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category

async def delete_category(session: AsyncSession, category_id: int) -> bool:
    category = await get_category(session, category_id)
    if category:
        await session.delete(category)
        await session.commit()
        return True
    return False

# ================= PRODUCT CRUD =================

async def get_products_by_category(session: AsyncSession, category_id: int) -> List[Product]:
    stmt = select(Product).where(Product.category_id == category_id, Product.is_active == True).order_by(Product.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_all_products(session: AsyncSession) -> List[Product]:
    stmt = select(Product).order_by(Product.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_product(session: AsyncSession, product_id: int) -> Optional[Product]:
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def create_product(
    session: AsyncSession,
    category_id: int,
    title: str,
    emoji: str = "📦",
    description: Optional[str] = None,
    custom_emoji_id: Optional[str] = None,
    image_url: Optional[str] = None
) -> Product:
    product = Product(
        category_id=category_id,
        title=title,
        emoji=emoji,
        description=description,
        custom_emoji_id=custom_emoji_id,
        image_url=image_url
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product

async def search_products(session: AsyncSession, query: str) -> List[Product]:
    """
    Search for active products by title or description keyword.
    """
    search_term = f"%{query.strip().lower()}%"
    stmt = (
        select(Product)
        .where(
            Product.is_active == True,
            (func.lower(Product.title).like(search_term)) |
            (func.lower(Product.description).like(search_term))
        )
        .order_by(Product.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def delete_product(session: AsyncSession, product_id: int) -> bool:
    product = await get_product(session, product_id)
    if product:
        await session.delete(product)
        await session.commit()
        return True
    return False

# ================= VARIANT CRUD =================

from sqlalchemy.orm import selectinload

async def get_variants_by_product(session: AsyncSession, product_id: int) -> List[Variant]:
    stmt = select(Variant).options(selectinload(Variant.product)).where(Variant.product_id == product_id, Variant.is_active == True).order_by(Variant.price)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_all_variants(session: AsyncSession) -> List[Variant]:
    stmt = select(Variant).options(selectinload(Variant.product)).order_by(Variant.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_variant(session: AsyncSession, variant_id: int) -> Optional[Variant]:
    stmt = select(Variant).options(selectinload(Variant.product)).where(Variant.id == variant_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def create_variant(
    session: AsyncSession,
    product_id: int,
    name: str,
    price: float,
    variant_type: str = "Private",
    detailed_description: Optional[str] = None
) -> Variant:
    variant = Variant(
        product_id=product_id,
        name=name,
        price=price,
        variant_type=variant_type,
        detailed_description=detailed_description
    )
    session.add(variant)
    await session.commit()
    await session.refresh(variant)
    return variant

async def delete_variant(session: AsyncSession, variant_id: int) -> bool:
    variant = await get_variant(session, variant_id)
    if variant:
        await session.delete(variant)
        await session.commit()
        return True
    return False

# ================= STOCK CRUD =================

async def get_available_stock_count(session: AsyncSession, variant_id: int) -> int:
    stmt = select(func.count(Stock.id)).where(Stock.variant_id == variant_id, Stock.is_used == False)
    result = await session.execute(stmt)
    return result.scalar() or 0

async def get_product_total_stock_count(session: AsyncSession, product_id: int) -> int:
    stmt = (
        select(func.count(Stock.id))
        .join(Variant, Stock.variant_id == Variant.id)
        .where(Variant.product_id == product_id, Stock.is_used == False)
    )
    result = await session.execute(stmt)
    return result.scalar() or 0

async def add_stock_bulk(session: AsyncSession, variant_id: int, items: List[str]) -> int:
    added = 0
    for item in items:
        clean_item = item.strip()
        if clean_item:
            session.add(Stock(variant_id=variant_id, content=clean_item, is_used=False))
            added += 1
    await session.commit()
    return added

async def pop_available_stock(session: AsyncSession, variant_id: int) -> Optional[Stock]:
    stmt = (
        select(Stock)
        .where(Stock.variant_id == variant_id, Stock.is_used == False)
        .order_by(Stock.id.asc())
        .limit(1)
        .with_for_update()
    )
    result = await session.execute(stmt)
    stock = result.scalar_one_or_none()
    return stock

async def get_total_active_stock(session: AsyncSession) -> int:
    stmt = select(func.count(Stock.id)).where(Stock.is_used == False)
    result = await session.execute(stmt)
    return result.scalar() or 0

# ================= ORDER CRUD =================

async def fulfill_order(
    session: AsyncSession,
    user_id: int,
    variant_id: int,
    amount: float
) -> Tuple[Optional[Order], Optional[str]]:
    """
    Deducts balance, consumes 1 stock item, creates Order, credits referral commission if applicable.
    Returns (Order, error_message).
    """
    user = await get_user(session, user_id)
    if not user or user.balance < amount:
        return None, "Insufficient balance in your wallet."

    variant = await get_variant(session, variant_id)
    if not variant:
        return None, "Product variant not found."

    stock = await pop_available_stock(session, variant_id)
    if not stock:
        return None, "Sorry, this item is currently out of stock."

    # Mark stock used
    stock.is_used = True
    stock.sold_at = datetime.datetime.utcnow()

    # Deduct user balance & update total_spent
    user.balance = round(user.balance - amount, 2)
    user.total_spent = round(user.total_spent + amount, 2)

    # Create order
    order = Order(
        user_id=user_id,
        variant_id=variant_id,
        amount=amount,
        delivered_content=stock.content,
        created_at=datetime.datetime.utcnow()
    )
    session.add(order)
    await session.flush() # Flush to populate order.id

    stock.order_id = order.id

    # Handle referral commission
    if user.referrer_id and config.REFERRAL_BONUS_PERCENT > 0:
        commission = round((amount * config.REFERRAL_BONUS_PERCENT) / 100, 2)
        if commission > 0:
            referrer = await get_user(session, user.referrer_id)
            if referrer:
                referrer.balance = round(referrer.balance + commission, 2)

    await session.commit()
    await session.refresh(order)
    return order, None

async def get_user_orders(session: AsyncSession, user_id: int, limit: int = 10) -> List[Order]:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_total_orders_and_revenue(session: AsyncSession) -> Tuple[int, float]:
    orders_count_stmt = select(func.count(Order.id))
    revenue_stmt = select(func.sum(Order.amount))
    
    count_res = await session.execute(orders_count_stmt)
    revenue_res = await session.execute(revenue_stmt)
    
    count = count_res.scalar() or 0
    revenue = revenue_res.scalar() or 0.0
    return count, round(revenue, 2)

async def get_orders_today_count(session: AsyncSession) -> int:
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.count(Order.id)).where(Order.created_at >= today_start)
    result = await session.execute(stmt)
    return result.scalar() or 0

# ================= DEPOSIT CRUD =================

async def create_deposit(
    session: AsyncSession,
    user_id: int,
    amount: float,
    utr_number: Optional[str] = None,
    proof_file_id: Optional[str] = None
) -> Deposit:
    deposit = Deposit(
        user_id=user_id,
        amount=round(amount, 2),
        utr_number=utr_number,
        proof_file_id=proof_file_id,
        status="PENDING",
        created_at=datetime.datetime.utcnow()
    )
    session.add(deposit)
    await session.commit()
    await session.refresh(deposit)
    return deposit

async def get_deposit(session: AsyncSession, deposit_id: int) -> Optional[Deposit]:
    stmt = select(Deposit).where(Deposit.id == deposit_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_pending_deposits(session: AsyncSession) -> List[Deposit]:
    stmt = select(Deposit).where(Deposit.status == "PENDING").order_by(Deposit.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def approve_deposit(session: AsyncSession, deposit_id: int) -> Tuple[Optional[Deposit], Optional[User]]:
    deposit = await get_deposit(session, deposit_id)
    if not deposit or deposit.status != "PENDING":
        return None, None

    deposit.status = "APPROVED"
    deposit.approved_at = datetime.datetime.utcnow()

    user = await get_user(session, deposit.user_id)
    if user:
        user.balance = round(user.balance + deposit.amount, 2)

    await session.commit()
    await session.refresh(deposit)
    if user:
        await session.refresh(user)
    return deposit, user

async def reject_deposit(session: AsyncSession, deposit_id: int) -> Optional[Deposit]:
    deposit = await get_deposit(session, deposit_id)
    if not deposit or deposit.status != "PENDING":
        return None

    deposit.status = "REJECTED"
    await session.commit()
    await session.refresh(deposit)
    return deposit

async def seed_initial_data(session: AsyncSession):
    """
    Seeds complete real SAM STORE catalog across all digital categories
    with detailed specifications, duration plans, and zero dummy stock.
    """
    # 1. Standardize Categories
    cats_data = [
        ("OTT & Streaming", "🍿", 1),
        ("AI Tools & Productivity", "🤖", 2),
        ("VPN Services", "🛡️", 3),
        ("Education & Developer", "🎓", 4),
        ("Gaming & Utilities", "🎮", 5),
        ("Freebies & Deals", "🎁", 6),
    ]

    # Clean old duplicate legacy category names if any
    legacy_cleanup = ["Streaming Services", "Legally paid services", "Education & Tools", "Vpn Services", "Freebies", "Ai tools", "PS5 Games", "🎬 OTT & Streaming", "🤖 🤖 AI Tools & Productivity", "🛡️ 🛡️ VPN Services", "🎓 🎓 Education & Developer", "🎮 🎮 Gaming & Utilities", "🎁 🎁 Freebies & Deals"]
    for old_name in legacy_cleanup:
        old_cat = (await session.execute(select(Category).where(Category.name == old_name))).scalar_one_or_none()
        if old_cat:
            # Check if any products under it
            prods = (await session.execute(select(Product).where(Product.category_id == old_cat.id))).scalars().all()
            if not prods:
                await session.delete(old_cat)
            else:
                # rename to clean version if applicable
                if "Streaming" in old_name:
                    old_cat.name = "🍿 OTT & Streaming"
                    old_cat.emoji = "🍿"
                elif "AI" in old_name or "Ai" in old_name:
                    old_cat.name = "🤖 AI Tools & Productivity"
                    old_cat.emoji = "🤖"
                elif "VPN" in old_name or "Vpn" in old_name:
                    old_cat.name = "🛡️ VPN Services"
                    old_cat.emoji = "🛡️"
                elif "Education" in old_name:
                    old_cat.name = "🎓 Education & Developer"
                    old_cat.emoji = "🎓"
                elif "Gaming" in old_name or "PS5" in old_name:
                    old_cat.name = "🎮 Gaming & Utilities"
                    old_cat.emoji = "🎮"
                elif "Freebie" in old_name:
                    old_cat.name = "🎁 Freebies & Deals"
                    old_cat.emoji = "🎁"
    await session.commit()

    cats_dict = {}
    for name, emoji, order in cats_data:
        stmt = select(Category).where(Category.name == name)
        res = await session.execute(stmt)
        cat = res.scalars().first()
        if not cat:
            cat = Category(name=name, emoji=emoji, sort_order=order)
            session.add(cat)
            await session.flush()
        cats_dict[name] = cat

    async def ensure_prod(cat_name, title, emoji, desc, variants_list, custom_emoji_id=None):
        cat = cats_dict.get(cat_name)
        if not cat:
            return
        stmt = select(Product).where(Product.title == title)
        res = await session.execute(stmt)
        prod = res.scalars().first()
        if not prod:
            prod = Product(category_id=cat.id, title=title, emoji=emoji, description=desc, custom_emoji_id=custom_emoji_id)
            session.add(prod)
            await session.flush()
        elif custom_emoji_id:
            prod.custom_emoji_id = custom_emoji_id
            await session.flush()
        
        for v_name, v_price, v_type, v_spec in variants_list:
            v_stmt = select(Variant).where(Variant.product_id == prod.id, Variant.name == v_name)
            v_res = await session.execute(v_stmt)
            if not v_res.scalars().first():
                session.add(Variant(
                    product_id=prod.id,
                    name=v_name,
                    price=v_price,
                    variant_type=v_type,
                    detailed_description=v_spec
                ))

    # --- 1. OTT & Streaming ---
    await ensure_prod(
        "OTT & Streaming", "Netflix Premium 4K UHD", "🍿",
        "Official Netflix Ultra HD 4K streaming accounts with private or shared profiles.",
        [
            ("1 Month Private Profile", 129.0, "Private Profile",
             "✨ <b>Netflix 4K UHD - 1 Month Private Profile</b>\n\n"
             "✦ <b>Quality:</b> 4K Ultra HD + HDR & Dolby Atmos\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen (Pin Locked)\n"
             "✦ <b>Devices:</b> Smart TV, Mobile, Laptop, Tablet, PC\n"
             "✦ <b>Warranty:</b> 30 Days Replacement Guarantee\n"
             "✦ <b>Rules:</b> Do not change password or email\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("3 Months Private Profile", 359.0, "Private Profile",
             "✨ <b>Netflix 4K UHD - 3 Months Private Profile</b>\n\n"
             "✦ <b>Quality:</b> 4K Ultra HD + HDR\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen (Your Own Pin)\n"
             "✦ <b>Warranty:</b> 90 Days Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("6 Months Private Profile", 679.0, "Private Profile",
             "✨ <b>Netflix 4K UHD - 6 Months Private Profile</b>\n\n"
             "✦ <b>Quality:</b> Ultra HD 4K Quality\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen\n"
             "✦ <b>Warranty:</b> 180 Days Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("12 Months Private Profile", 1249.0, "Private Profile",
             "✨ <b>Netflix 4K UHD - 12 Months (1 Year)</b>\n\n"
             "✦ <b>Quality:</b> Ultra HD 4K Quality (1 Year)\n"
             "✦ <b>Screen:</b> 1 Dedicated Pin-locked Profile\n"
             "✦ <b>Warranty:</b> 365 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("1 Month Shared Profile", 99.0, "Shared Profile",
             "✨ <b>Netflix 4K UHD - 1 Month Shared Profile</b>\n\n"
             "✦ <b>Quality:</b> Ultra HD 4K Quality\n"
             "✦ <b>Screen:</b> Shared Profile\n"
             "✦ <b>Warranty:</b> 30 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
        ]
    )

    await ensure_prod(
        "OTT & Streaming", "Amazon Prime Video", "📦",
        "Amazon Prime Video Premium with 4K UHD HDR streaming.",
        [
            ("1 Month Private Profile", 79.0, "Private Profile",
             "✨ <b>Amazon Prime Video - 1 Month Private Profile</b>\n\n"
             "✦ <b>Quality:</b> 4K Ultra HD + HDR\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen (Pin Locked)\n"
             "✦ <b>Devices:</b> Smart TV, Mobile, Laptop, PC\n"
             "✦ <b>Warranty:</b> 30 Days Full Replacement Warranty\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("6 Months Private Profile", 299.0, "Private Profile",
             "✨ <b>Amazon Prime Video - 6 Months Private Profile</b>\n\n"
             "✦ <b>Quality:</b> 4K Ultra HD Streaming\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen\n"
             "✦ <b>Warranty:</b> 180 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("12 Months Private Profile", 499.0, "Private Profile",
             "✨ <b>Amazon Prime Video - 12 Months (1 Year)</b>\n\n"
             "✦ <b>Quality:</b> 4K Ultra HD Streaming\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen\n"
             "✦ <b>Warranty:</b> 365 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
        ]
    )

    await ensure_prod(
        "OTT & Streaming", "YouTube Premium", "🔴",
        "Ad-free YouTube & YouTube Music with background playback & downloads.",
        [
            ("1 Month Family Invite", 49.0, "Invite Link",
             "✨ <b>YouTube Premium - 1 Month Plan</b>\n\n"
             "✦ <b>Features:</b> Ad-Free YouTube + YouTube Music\n"
             "✦ <b>Playback:</b> Background play & offline downloads\n"
             "✦ <b>Delivery:</b> Instant activation invite link"),
            ("12 Months Family Invite", 299.0, "Invite Link",
             "✨ <b>YouTube Premium - 1 Year Plan</b>\n\n"
             "✦ <b>Features:</b> 12 Months Ad-Free YouTube\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Instant activation"),
        ]
    )

    await ensure_prod(
        "OTT & Streaming", "Spotify Premium", "🎵",
        "Spotify Premium individual & family promo codes with high quality audio.",
        [
            ("3 Months Promo Code", 99.0, "Redeem Code",
             "✨ <b>Spotify Premium - 3 Months Code</b>\n\n"
             "✦ <b>Quality:</b> 320kbps Lossless Audio\n"
             "✦ <b>Features:</b> Ad-free music & unlimited skips\n"
             "✦ <b>Delivery:</b> Instant Redeem Link"),
            ("12 Months Individual", 299.0, "Redeem Code",
             "✨ <b>Spotify Premium - 1 Year Code</b>\n\n"
             "✦ <b>Features:</b> 1 Year Ad-Free Music\n"
             "✦ <b>Warranty:</b> 1 Year Warranty\n"
             "✦ <b>Delivery:</b> Instant Activation"),
        ],
        custom_emoji_id="5868508172108435919"
    )

    await ensure_prod(
        "OTT & Streaming", "Crunchyroll Mega Fan", "🍥",
        "Ad-free anime streaming in full HD with offline downloads.",
        [
            ("1 Month Mega Fan", 69.0, "Private Account",
             "✨ <b>Crunchyroll Mega Fan - 1 Month</b>\n\n"
             "✦ <b>Quality:</b> 1080p HD Anime Streaming\n"
             "✦ <b>Features:</b> Simulcast 1 hour after Japan\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
            ("12 Months Mega Fan", 399.0, "Private Account",
             "✨ <b>Crunchyroll Mega Fan - 1 Year</b>\n\n"
             "✦ <b>Quality:</b> 1080p Full Access\n"
             "✦ <b>Warranty:</b> 365 Days Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ]
    )

    # --- 2. AI Tools & Productivity ---
    await ensure_prod(
        "AI Tools & Productivity", "ChatGPT Plus (GPT-4o)", "🤖",
        "Official OpenAI ChatGPT Plus subscription with GPT-4o, DALL-E 3 & plugins.",
        [
            ("1 Month Private Account", 499.0, "Private Account",
             "✨ <b>ChatGPT Plus - 1 Month Private</b>\n\n"
             "✦ <b>Model:</b> GPT-4o, GPT-4, DALL-E 3, Browsing\n"
             "✦ <b>Access:</b> Dedicated Private Login (Email+Pass)\n"
             "✦ <b>Warranty:</b> 30 Days Full Replacement\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ]
    )

    await ensure_prod(
        "AI Tools & Productivity", "Claude 3.5 Sonnet Pro", "🧠",
        "Anthropic Claude Pro with 5x usage on Claude 3.5 Sonnet & Artifacts.",
        [
            ("1 Month Private Account", 549.0, "Private Account",
             "✨ <b>Claude 3.5 Sonnet Pro - 1 Month</b>\n\n"
             "✦ <b>Features:</b> Claude 3.5 Sonnet & Opus, Projects\n"
             "✦ <b>Access:</b> Dedicated Private Login\n"
             "✦ <b>Warranty:</b> 30 Days Replacement\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ]
    )

    await ensure_prod(
        "AI Tools & Productivity", "Canva Pro", "🎨",
        "Unlock 100M+ premium photos, templates, fonts & brand kits on Canva.",
        [
            ("1 Year Team Invite", 99.0, "Invite Link",
             "✨ <b>Canva Pro - 1 Year Plan</b>\n\n"
             "✦ <b>Features:</b> All Pro Templates, Background Remover, Magic AI\n"
             "✦ <b>Activation:</b> Added to your own existing Canva email\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Invitation Link"),
            ("Lifetime Pro Access", 199.0, "Invite Link",
             "✨ <b>Canva Pro - Lifetime Access</b>\n\n"
             "✦ <b>Features:</b> Unlimited Pro Tools & AI Suite\n"
             "✦ <b>Warranty:</b> Lifetime Guarantee\n"
             "✦ <b>Delivery:</b> Instant Activation"),
        ]
    )

    await ensure_prod(
        "AI Tools & Productivity", "CapCut Pro", "✂️",
        "CapCut Pro video editor with premium AI filters, effects & cloud storage.",
        [
            ("6 Months Private Login", 299.0, "Private Account",
             "✨ <b>CapCut Pro - 6 Months Plan</b>\n\n"
             "✦ <b>Features:</b> Auto Captions, 4K 60FPS Export, AI Tools\n"
             "✦ <b>Devices:</b> PC, Mac, Android, iOS\n"
             "✦ <b>Warranty:</b> 180 Days Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
            ("12 Months Private Login", 499.0, "Private Account",
             "✨ <b>CapCut Pro - 1 Year Plan</b>\n\n"
             "✦ <b>Features:</b> 12 Months All Pro Effects & Tools\n"
             "✦ <b>Warranty:</b> 365 Days Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ]
    )

    # --- 3. VPN Services ---
    await ensure_prod(
        "VPN Services", "NordVPN Premium", "🌐",
        "High-speed ultra secure VPN with Threat Protection & Meshnet.",
        [
            ("1 Year Premium Account", 199.0, "Private Account",
             "✨ <b>NordVPN Premium - 1 Year Plan</b>\n\n"
             "✦ <b>Servers:</b> 6000+ Servers in 110 Countries\n"
             "✦ <b>Features:</b> Double VPN, CyberSec, AdBlock\n"
             "✦ <b>Warranty:</b> 365 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ]
    )

    # --- 4. Gaming & Utilities ---
    await ensure_prod(
        "Gaming & Utilities", "Telegram Premium", "✈️",
        "Official Telegram Premium subscription for 4GB uploads, custom emojis & badges.",
        [
            ("3 Months Gift Code", 499.0, "Gift Link",
             "✨ <b>Telegram Premium - 3 Months</b>\n\n"
             "✦ <b>Features:</b> Custom Emojis, 4GB Uploads, Fast Downloads\n"
             "✦ <b>Delivery:</b> Instant Gift Link / Activation"),
            ("12 Months Gift Code", 1499.0, "Gift Link",
             "✨ <b>Telegram Premium - 1 Year</b>\n\n"
             "✦ <b>Features:</b> 1 Year Full Telegram Premium Perks\n"
             "✦ <b>Delivery:</b> Instant Activation"),
        ]
    )

    await ensure_prod(
        "Gaming & Utilities", "Discord Nitro", "💬",
        "Discord Nitro with 2 Server Boosts, HD streaming, custom emojis & stickers.",
        [
            ("1 Month Nitro with 2 Boosts", 149.0, "Gift Link",
             "✨ <b>Discord Nitro - 1 Month</b>\n\n"
             "✦ <b>Features:</b> 2 Server Boosts, 500MB Uploads, HD Stream\n"
             "✦ <b>Delivery:</b> Instant Gift Link"),
        ]
    )

    await session.commit()

async def purge_old_dummy_stocks(session: AsyncSession):
    """
    Deletes any legacy dummy demo stocks that contain mock test emails
    so the database only contains 100% real uploaded inventory.
    """
    await session.execute(
        delete(Stock).where(
            (Stock.content.like("%@ottmail.com%")) |
            (Stock.content.like("%test_account%")) |
            (Stock.content.like("%sam_user%")) |
            (Stock.content.like("%sam_shared%"))
        )
    )
    await session.commit()

async def clear_all_catalog_data(session: AsyncSession):
    """
    Clears all categories, products, variants, and stock so the admin
    can start with a 100% fresh, clean catalog.
    """
    await session.execute(delete(Stock))
    await session.execute(delete(Variant))
    await session.execute(delete(Product))
    await session.execute(delete(Category))
    await session.commit()
