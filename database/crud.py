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
    stmt = select(Category).where(Category.is_active == True).order_by(Category.sort_order, Category.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

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

async def delete_product(session: AsyncSession, product_id: int) -> bool:
    product = await get_product(session, product_id)
    if product:
        await session.delete(product)
        await session.commit()
        return True
    return False

# ================= VARIANT CRUD =================

async def get_variants_by_product(session: AsyncSession, product_id: int) -> List[Variant]:
    stmt = select(Variant).where(Variant.product_id == product_id, Variant.is_active == True).order_by(Variant.price)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_all_variants(session: AsyncSession) -> List[Variant]:
    stmt = select(Variant).order_by(Variant.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_variant(session: AsyncSession, variant_id: int) -> Optional[Variant]:
    stmt = select(Variant).where(Variant.id == variant_id)
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

# ================= SEED INITIAL STORE DATA =================

async def seed_initial_data(session: AsyncSession):
    """
    Seeds initial categories and products matching the screenshots
    if the database is currently empty.
    """
    cat_check = await session.execute(select(func.count(Category.id)))
    if (cat_check.scalar() or 0) > 0:
        return # Already seeded

    # Seed Categories
    cat1 = Category(name="Streaming Services", emoji="🎬", sort_order=1)
    cat2 = Category(name="Legally paid services", emoji="💼", sort_order=2)
    cat3 = Category(name="Education & Tools", emoji="🎓", sort_order=3)
    cat4 = Category(name="Vpn Services", emoji="🛡️", sort_order=4)
    cat5 = Category(name="Freebies", emoji="🎁", sort_order=5)
    cat6 = Category(name="Ai tools", emoji="🤖", sort_order=6)
    cat7 = Category(name="PS5 Games", emoji="🎮", sort_order=7)

    session.add_all([cat1, cat2, cat3, cat4, cat5, cat6, cat7])
    await session.commit()

    # Seed Products under Streaming Services
    p_prime = Product(
        category_id=cat1.id,
        title="Prime Video",
        emoji="📦",
        description="Amazon Prime Video Premium subscriptions with 4K UHD streaming."
    )
    p_yt = Product(
        category_id=cat1.id,
        title="YouTube Premium",
        emoji="📦",
        description="Ad-free YouTube & YouTube Music with background playback."
    )
    p_netflix = Product(
        category_id=cat1.id,
        title="Netflix Premium 4K",
        emoji="📦",
        description="Official Netflix Ultra HD 4K streaming accounts with private or shared profiles."
    )
    p_spotify = Product(
        category_id=cat1.id,
        title="Spotify Promocodes",
        emoji="📦",
        description="Spotify Premium individual or family redeem codes."
    )
    p_zee5 = Product(
        category_id=cat1.id,
        title="Zee5 Premium",
        emoji="📦",
        description="Zee5 All-Access plan with HD streaming and movies."
    )
    p_apple = Product(
        category_id=cat1.id,
        title="Apple Music",
        emoji="📦",
        description="Apple Music Lossless audio subscriptions."
    )
    p_hotstar = Product(
        category_id=cat1.id,
        title="Jio Hotstar Super/Premium",
        emoji="📦",
        description="Disney+ Hotstar live cricket & movie streaming plans."
    )
    p_crunchy = Product(
        category_id=cat1.id,
        title="Crunchyroll Mega Fan",
        emoji="📦",
        description="Ad-free anime in 1080p with offline viewing."
    )

    session.add_all([p_prime, p_yt, p_netflix, p_spotify, p_zee5, p_apple, p_hotstar, p_crunchy])
    await session.commit()

    # Seed Variants for Netflix with rich descriptions (matching image 5)
    v1 = Variant(
        product_id=p_netflix.id,
        name="1 Month Private Profile",
        price=129.0,
        variant_type="Private Profile",
        detailed_description=(
            "✨ <b>Netflix 4K UHD - 1 Month Private Profile</b>\n\n"
            "✦ <b>Quality:</b> 4K Ultra HD + HDR & Dolby Atmos\n"
            "✦ <b>Screen:</b> 1 Dedicated Screen (Pin Locked)\n"
            "✦ <b>Devices:</b> Smart TV, Mobile, Laptop, Tablet, PC\n"
            "✦ <b>Warranty:</b> 30 Days Replacement Guarantee\n"
            "✦ <b>Rules:</b> Do not change password or email\n"
            "✦ <b>Delivery:</b> Instant Automated Delivery upon purchase"
        )
    )
    v2 = Variant(
        product_id=p_netflix.id,
        name="3 Months Private Profile",
        price=359.0,
        variant_type="Private Profile",
        detailed_description=(
            "✨ <b>Netflix 4K UHD - 3 Months Private Profile</b>\n\n"
            "✦ <b>Quality:</b> 4K Ultra HD + HDR\n"
            "✦ <b>Screen:</b> 1 Dedicated Screen (Your Own Pin)\n"
            "✦ <b>Warranty:</b> 90 Days Full Warranty\n"
            "✦ <b>Delivery:</b> Instant Automated Delivery"
        )
    )
    v3 = Variant(
        product_id=p_netflix.id,
        name="6 Months Private Profile",
        price=679.0,
        variant_type="Private Profile",
        detailed_description=(
            "✨ <b>Netflix 4K UHD - 6 Months Private Profile</b>\n\n"
            "✦ <b>Quality:</b> Ultra HD 4K Quality\n"
            "✦ <b>Screen:</b> 1 Dedicated Screen\n"
            "✦ <b>Warranty:</b> 180 Days Full Warranty\n"
            "✦ <b>Delivery:</b> Instant Automated Delivery"
        )
    )
    v4 = Variant(
        product_id=p_netflix.id,
        name="12 Months Private Profile",
        price=1249.0,
        variant_type="Private Profile",
        detailed_description=(
            "✨ <b>Netflix 4K UHD - 12 Months Private Profile</b>\n\n"
            "✦ <b>Quality:</b> Ultra HD 4K Quality (1 Year)\n"
            "✦ <b>Screen:</b> 1 Dedicated Pin-locked Profile\n"
            "✦ <b>Warranty:</b> 365 Days Replacement Guarantee\n"
            "✦ <b>Delivery:</b> Instant Automated Delivery"
        )
    )
    v5 = Variant(
        product_id=p_netflix.id,
        name="1 Month Shared Profile",
        price=99.0,
        variant_type="Shared Profile",
        detailed_description=(
            "✨ <b>Netflix 4K UHD - 1 Month Shared Profile</b>\n\n"
            "✦ <b>Quality:</b> Ultra HD 4K Quality\n"
            "✦ <b>Screen:</b> Shared Profile\n"
            "✦ <b>Warranty:</b> 30 Days Replacement Guarantee\n"
            "✦ <b>Delivery:</b> Instant Automated Delivery"
        )
    )

    session.add_all([v1, v2, v3, v4, v5])
    await session.commit()

    # Add sample stock for 1 Month Private Profile
    s1 = Stock(variant_id=v1.id, content="Email: sam_user1@ottmail.com | Pass: PremiumPass99! | Profile: User 1 | PIN: 1234")
    s2 = Stock(variant_id=v1.id, content="Email: sam_user2@ottmail.com | Pass: UltraSafe88# | Profile: User 2 | PIN: 5678")
    s3 = Stock(variant_id=v5.id, content="Email: sam_shared1@ottmail.com | Pass: SharedSub123 | Profile: Shared 3")
    session.add_all([s1, s2, s3])
    await session.commit()
