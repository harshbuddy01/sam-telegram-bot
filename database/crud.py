import datetime
from typing import Optional, List, Tuple
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from database.models import User, Category, Product, Variant, Stock, Order, Deposit
from utils.emojis import Emojis, CustomEmojis, clean_button_text
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

async def get_users_with_balance(session: AsyncSession, limit: int = 50) -> List[User]:
    """Get all users who have an active positive wallet balance."""
    stmt = select(User).where(User.balance > 0).order_by(User.balance.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_recent_users(session: AsyncSession, limit: int = 30) -> List[User]:
    """Get most recently registered users."""
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_total_wallet_liabilities(session: AsyncSession) -> float:
    """Get total balance held across all user wallets."""
    stmt = select(func.coalesce(func.sum(User.balance), 0.0))
    result = await session.execute(stmt)
    return float(result.scalar() or 0.0)

async def search_users(session: AsyncSession, query: str, limit: int = 20) -> List[User]:
    """Search users by numeric Telegram ID, username, or full name."""
    query = query.strip()
    if query.isdigit():
        target_id = int(query)
        stmt = select(User).where((User.telegram_id == target_id) | (User.id == target_id)).limit(limit)
    else:
        clean_q = f"%{query.lstrip('@')}%"
        stmt = select(User).where(
            (User.username.ilike(clean_q)) | (User.full_name.ilike(clean_q))
        ).order_by(User.balance.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())

# ================= CATEGORY CRUD =================

async def get_active_categories(session: AsyncSession) -> List[Category]:
    """Return ALL active categories (including newly created ones with no products yet)."""
    stmt = select(Category).where(Category.is_active == True).order_by(Category.sort_order, Category.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_all_categories(session: AsyncSession) -> List[Category]:
    stmt = select(Category).where(Category.is_active == True).order_by(Category.sort_order, Category.id)
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
    if not category:
        return False
    
    # 1. Deactivate all products and variants under this category, and delete unsold stock
    prods_stmt = select(Product).where(Product.category_id == category_id)
    prods_res = await session.execute(prods_stmt)
    products = list(prods_res.scalars().all())
    for prod in products:
        await delete_product(session, prod.id)
    
    # 2. Deactivate category
    category.is_active = False
    await session.commit()
    return True

# ================= PRODUCT CRUD =================

async def get_products_by_category(session: AsyncSession, category_id: int) -> List[Product]:
    stmt = select(Product).where(Product.category_id == category_id, Product.is_active == True).order_by(Product.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_all_products(session: AsyncSession) -> List[Product]:
    stmt = select(Product).where(Product.is_active == True).order_by(Product.id)
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

async def update_category_details(
    session: AsyncSession,
    category_id: int,
    name: str,
    emoji: Optional[str] = "📁",
    custom_emoji_id: Optional[str] = None
) -> Optional[Category]:
    category = await get_category(session, category_id)
    if category:
        category.name = name
        if emoji:
            category.emoji = emoji
        if custom_emoji_id:
            category.custom_emoji_id = custom_emoji_id
        await session.commit()
        await session.refresh(category)
        return category
    return None

async def update_product_details(
    session: AsyncSession,
    product_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    emoji: Optional[str] = None,
    custom_emoji_id: Optional[str] = None
) -> Optional[Product]:
    product = await get_product(session, product_id)
    if product:
        if title:
            product.title = title
        if description is not None:
            product.description = description
        if emoji:
            product.emoji = emoji
        if custom_emoji_id:
            product.custom_emoji_id = custom_emoji_id
        await session.commit()
        await session.refresh(product)
        return product
    return None

async def delete_product(session: AsyncSession, product_id: int) -> bool:
    product = await get_product(session, product_id)
    if not product:
        return False
        
    vars_stmt = select(Variant).where(Variant.product_id == product_id)
    vars_res = await session.execute(vars_stmt)
    variants = list(vars_res.scalars().all())
    for var in variants:
        await delete_variant(session, var.id)
        
    product.is_active = False
    await session.commit()
    return True

# ================= VARIANT CRUD =================

from sqlalchemy.orm import selectinload

async def get_variants_by_product(session: AsyncSession, product_id: int) -> List[Variant]:
    stmt = select(Variant).options(selectinload(Variant.product)).where(Variant.product_id == product_id, Variant.is_active == True).order_by(Variant.price, Variant.id)
    result = await session.execute(stmt)
    all_vars = list(result.scalars().all())
    
    # Deduplicate in-memory to guarantee customers only see distinct plans
    unique_vars = []
    seen_keys = set()
    for v in all_vars:
        norm_name = clean_button_text(v.name).lower() if v.name else ""
        key = (norm_name, round(v.price, 2))
        if key not in seen_keys:
            seen_keys.add(key)
            unique_vars.append(v)
    return unique_vars

async def get_all_variants(session: AsyncSession) -> List[Variant]:
    stmt = select(Variant).options(selectinload(Variant.product)).where(Variant.is_active == True).order_by(Variant.id)
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
    detailed_description: Optional[str] = None,
    fulfillment_type: str = "AUTOMATIC",
    manual_dispatch_time: str = "1–2 Hours",
    input_prompt: Optional[str] = None,
    requires_customer_input: bool = True,
    stock_quantity: int = 50
) -> Variant:
    clean_name = clean_button_text(name) or name
    # Check if an existing active variant for this product already exists with the same name
    stmt = select(Variant).where(
        Variant.product_id == product_id,
        Variant.name == clean_name,
        Variant.is_active == True
    )
    res = await session.execute(stmt)
    existing = res.scalars().first()
    if existing:
        existing.price = price
        existing.variant_type = variant_type
        if detailed_description:
            existing.detailed_description = detailed_description
        existing.fulfillment_type = fulfillment_type
        existing.manual_dispatch_time = manual_dispatch_time
        if input_prompt:
            existing.input_prompt = input_prompt
        existing.requires_customer_input = requires_customer_input
        await session.commit()
        await session.refresh(existing)
        return existing

    variant = Variant(
        product_id=product_id,
        name=clean_name,
        price=price,
        variant_type=variant_type,
        detailed_description=detailed_description,
        fulfillment_type=fulfillment_type,
        manual_dispatch_time=manual_dispatch_time,
        input_prompt=input_prompt,
        requires_customer_input=requires_customer_input,
        stock_quantity=stock_quantity,
        is_active=True
    )
    session.add(variant)
    await session.commit()
    await session.refresh(variant)
    return variant

async def update_variant_details(
    session: AsyncSession,
    variant_id: int,
    name: Optional[str] = None,
    price: Optional[float] = None,
    variant_type: Optional[str] = None,
    detailed_description: Optional[str] = None,
    fulfillment_type: Optional[str] = None,
    manual_dispatch_time: Optional[str] = None,
    input_prompt: Optional[str] = None,
    requires_customer_input: Optional[bool] = None,
    stock_quantity: Optional[int] = None
) -> Optional[Variant]:
    variant = await get_variant(session, variant_id)
    if variant:
        if name is not None:
            variant.name = name
        if price is not None:
            variant.price = price
        if variant_type is not None:
            variant.variant_type = variant_type
        if detailed_description is not None:
            variant.detailed_description = detailed_description
        if fulfillment_type is not None:
            variant.fulfillment_type = fulfillment_type
        if manual_dispatch_time is not None:
            variant.manual_dispatch_time = manual_dispatch_time
        if input_prompt is not None:
            variant.input_prompt = input_prompt
        if requires_customer_input is not None:
            variant.requires_customer_input = requires_customer_input
        if stock_quantity is not None:
            variant.stock_quantity = stock_quantity
        await session.commit()
        await session.refresh(variant)
        return variant
    return None

async def delete_variant(session: AsyncSession, variant_id: int) -> bool:
    variant = await get_variant(session, variant_id)
    if not variant:
        return False
        
    await delete_unsold_stock_by_variant(session, variant_id)
    
    variant.is_active = False
    await session.commit()
    return True

# ================= STOCK CRUD =================

async def get_available_stock_count(session: AsyncSession, variant_id: int) -> int:
    variant = await get_variant(session, variant_id)
    if not variant:
        return 0
    if getattr(variant, "fulfillment_type", "AUTOMATIC") == "MANUAL":
        qty = getattr(variant, "stock_quantity", 0)
        return qty if qty is not None else 0
    stmt = select(func.count(Stock.id)).where(Stock.variant_id == variant_id, Stock.is_used == False)
    result = await session.execute(stmt)
    return result.scalar() or 0

async def get_batch_product_stock_counts(session: AsyncSession, product_ids: list[int]) -> dict[int, int]:
    """Get stock counts for multiple products in minimal queries instead of N+1."""
    if not product_ids:
        return {}
    
    counts = {pid: 0 for pid in product_ids}
    
    # Automatic stock: count unsold Stock rows per product
    stmt_auto = (
        select(Variant.product_id, func.count(Stock.id))
        .join(Stock, (Stock.variant_id == Variant.id) & (Stock.is_used == False))
        .where(
            Variant.product_id.in_(product_ids),
            Variant.is_active == True,
            Variant.fulfillment_type != "MANUAL"
        )
        .group_by(Variant.product_id)
    )
    for pid, cnt in (await session.execute(stmt_auto)).all():
        counts[pid] = counts.get(pid, 0) + (cnt or 0)
    
    # Manual stock: sum stock_quantity per product
    stmt_manual = (
        select(Variant.product_id, func.coalesce(func.sum(Variant.stock_quantity), 0))
        .where(
            Variant.product_id.in_(product_ids),
            Variant.is_active == True,
            Variant.fulfillment_type == "MANUAL"
        )
        .group_by(Variant.product_id)
    )
    for pid, qty in (await session.execute(stmt_manual)).all():
        counts[pid] = counts.get(pid, 0) + (qty or 0)
    
    return counts

async def get_product_total_stock_count(session: AsyncSession, product_id: int) -> int:
    variants = await get_variants_by_product(session, product_id)
    total_stock = 0
    for v in variants:
        if getattr(v, "fulfillment_type", "AUTOMATIC") == "MANUAL":
            qty = getattr(v, "stock_quantity", 0)
            total_stock += qty if qty is not None else 0
        else:
            stmt = select(func.count(Stock.id)).where(Stock.variant_id == v.id, Stock.is_used == False)
            res = await session.execute(stmt)
            total_stock += res.scalar() or 0
    return total_stock

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

async def get_unsold_stock_by_variant(session: AsyncSession, variant_id: int) -> List[Stock]:
    stmt = select(Stock).where(Stock.variant_id == variant_id, Stock.is_used == False).order_by(Stock.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def delete_unsold_stock_by_variant(session: AsyncSession, variant_id: int) -> int:
    stmt = delete(Stock).where(Stock.variant_id == variant_id, Stock.is_used == False)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0

# ================= ORDER CRUD (AUTOMATIC & MANUAL) =================

async def fulfill_order(
    session: AsyncSession,
    user_id: int,
    variant_id: int,
    amount: float,
    quantity: int = 1
) -> Tuple[Optional[Order], Optional[str]]:
    """
    Automatic Fulfillment: Deducts balance, consumes N pre-loaded stock items, creates one Order,
    credits referral commission if applicable.
    Returns (Order, error_message).
    """
    quantity = max(1, int(quantity))
    total_amount = round(amount * quantity, 2)

    user = await get_user(session, user_id)
    if not user or user.balance < total_amount:
        return None, f"Insufficient balance. Need {config.CURRENCY_SYMBOL}{total_amount:.2f}, you have {config.CURRENCY_SYMBOL}{user.balance:.2f}."

    variant = await get_variant(session, variant_id)
    if not variant:
        return None, "Product variant not found."

    # Pop N stock items
    stocks = []
    for _ in range(quantity):
        stock = await pop_available_stock(session, variant_id)
        if not stock:
            # Rollback already-drawn stocks conceptually — mark them unused again
            for s in stocks:
                s.is_used = False
                s.sold_at = None
            return None, f"Not enough stock available for qty={quantity}. Only {len(stocks)} item(s) left."
        stock.is_used = True
        stock.sold_at = datetime.datetime.utcnow()
        stocks.append(stock)

    # Deduct user balance & update total_spent
    user.balance = round(user.balance - total_amount, 2)
    user.total_spent = round(user.total_spent + total_amount, 2)

    # Bundle delivered content — "Account 1: ...\n\nAccount 2: ..." for qty>1
    if quantity == 1:
        delivered = stocks[0].content
    else:
        parts = []
        for i, s in enumerate(stocks, 1):
            parts.append(f"Account {i}:\n{s.content}")
        delivered = "\n\n".join(parts)

    # Create single order for the whole quantity
    now = datetime.datetime.utcnow()
    order = Order(
        user_id=user_id,
        variant_id=variant_id,
        amount=total_amount,
        quantity=quantity,
        status="COMPLETED",
        customer_input=None,
        delivered_content=delivered,
        created_at=now,
        fulfilled_at=now
    )
    session.add(order)
    await session.flush()

    for s in stocks:
        s.order_id = order.id

    # Handle referral commission
    if user.referrer_id and config.REFERRAL_BONUS_PERCENT > 0:
        commission = round((total_amount * config.REFERRAL_BONUS_PERCENT) / 100, 2)
        if commission > 0:
            referrer = await get_user(session, user.referrer_id)
            if referrer:
                referrer.balance = round(referrer.balance + commission, 2)

    await session.commit()
    await session.refresh(order)
    return order, None

async def create_manual_order(
    session: AsyncSession,
    user_id: int,
    variant_id: int,
    amount: float,
    customer_input: str,
    quantity: int = 1
) -> Tuple[Optional[Order], Optional[str]]:
    """
    Manual Fulfillment: Deducts wallet balance, records user's input/email,
    and sets status to PENDING_DISPATCH (dispatch within 1-2 hours).
    """
    quantity = max(1, int(quantity))
    total_amount = round(amount * quantity, 2)

    user = await get_user(session, user_id)
    if not user or user.balance < total_amount:
        return None, f"Insufficient balance. Need {config.CURRENCY_SYMBOL}{total_amount:.2f}, you have {config.CURRENCY_SYMBOL}{user.balance:.2f}."

    variant = await get_variant(session, variant_id)
    if not variant:
        return None, "Product variant not found."

    # Deduct balance
    user.balance = round(user.balance - total_amount, 2)
    user.total_spent = round(user.total_spent + total_amount, 2)

    # Decrement manual stock slots × quantity
    if getattr(variant, "stock_quantity", None) is not None and variant.stock_quantity > 0:
        variant.stock_quantity = max(0, variant.stock_quantity - quantity)

    # Create manual order
    if customer_input:
        input_str = customer_input.strip()
    elif not getattr(variant, "requires_customer_input", True):
        input_str = "None (Direct Admin Delivery)"
    else:
        input_str = "Direct 1-Click Purchase (Awaiting details)"

    # Append quantity note to input for admin visibility
    qty_note = f" [QTY: {quantity}]" if quantity > 1 else ""
    order = Order(
        user_id=user_id,
        variant_id=variant_id,
        amount=total_amount,
        quantity=quantity,
        status="PENDING_DISPATCH",
        customer_input=f"{input_str}{qty_note}",
        delivered_content="",
        created_at=datetime.datetime.utcnow(),
        fulfilled_at=None
    )
    session.add(order)
    await session.flush()

    # Handle referral commission
    if user.referrer_id and config.REFERRAL_BONUS_PERCENT > 0:
        commission = round((total_amount * config.REFERRAL_BONUS_PERCENT) / 100, 2)
        if commission > 0:
            referrer = await get_user(session, user.referrer_id)
            if referrer:
                referrer.balance = round(referrer.balance + commission, 2)

    await session.commit()
    await session.refresh(order)
    return order, None

async def fulfill_manual_order(
    session: AsyncSession,
    order_id: int,
    delivered_content: str
) -> Tuple[Optional[Order], Optional[User]]:
    """
    Admin fulfills a manual order: sets delivered content, marks COMPLETED,
    and returns (order, user) for instant dispatch notification.
    """
    stmt = select(Order).options(selectinload(Order.variant)).where(Order.id == order_id)
    res = await session.execute(stmt)
    order = res.scalar_one_or_none()

    if not order or order.status != "PENDING_DISPATCH":
        return None, None

    order.delivered_content = delivered_content.strip()
    order.status = "COMPLETED"
    order.fulfilled_at = datetime.datetime.utcnow()

    user = await get_user(session, order.user_id)
    await session.commit()
    await session.refresh(order)
    return order, user

async def cancel_and_refund_order(
    session: AsyncSession,
    order_id: int
) -> Tuple[Optional[Order], Optional[User]]:
    """
    Cancels a pending manual order and automatically refunds the user's wallet.
    """
    stmt = select(Order).where(Order.id == order_id)
    res = await session.execute(stmt)
    order = res.scalar_one_or_none()

    if not order or order.status != "PENDING_DISPATCH":
        return None, None

    order.status = "CANCELLED"
    user = await get_user(session, order.user_id)
    if user:
        user.balance = round(user.balance + order.amount, 2)
        user.total_spent = max(0.0, round(user.total_spent - order.amount, 2))

    await session.commit()
    await session.refresh(order)
    return order, user

async def get_pending_manual_orders(session: AsyncSession) -> List[Order]:
    stmt = select(Order).options(selectinload(Order.variant)).where(Order.status == "PENDING_DISPATCH").order_by(Order.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_order_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
    stmt = select(Order).options(selectinload(Order.variant), selectinload(Order.user)).where(Order.id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_recent_orders(session: AsyncSession, limit: int = 30) -> List[Order]:
    """
    Admin Audit Log: returns all recent orders (automatic and manual) across the entire store.
    """
    stmt = select(Order).options(selectinload(Order.variant), selectinload(Order.user)).order_by(Order.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def create_deposit_gateway(
    session: AsyncSession,
    user_id: int,
    amount: float,
    gateway: str = "MANUAL_UPI",
    gateway_order_id: Optional[str] = None,
    target_variant_id: Optional[int] = None
) -> Deposit:
    deposit = Deposit(
        user_id=user_id,
        amount=amount,
        gateway=gateway,
        gateway_order_id=gateway_order_id,
        target_variant_id=target_variant_id,
        status="PENDING"
    )
    session.add(deposit)
    await session.commit()
    await session.refresh(deposit)
    return deposit

async def credit_user_deposit_automated(
    session: AsyncSession,
    gateway_order_id: str,
    gateway_payment_id: Optional[str] = None
) -> Tuple[Optional[Deposit], Optional[User]]:
    stmt = select(Deposit).where(Deposit.gateway_order_id == gateway_order_id)
    res = await session.execute(stmt)
    deposit = res.scalar_one_or_none()

    if not deposit or deposit.status in ("APPROVED", "SUCCESS"):
        return None, None

    deposit.status = "SUCCESS"
    deposit.gateway_payment_id = gateway_payment_id
    deposit.approved_at = datetime.datetime.utcnow()

    user = await get_user(session, deposit.user_id)
    if user:
        user.balance = round(user.balance + deposit.amount, 2)

    await session.commit()
    await session.refresh(deposit)
    return deposit, user

async def get_user_orders(session: AsyncSession, user_id: int, limit: int = 10) -> List[Order]:
    stmt = (
        select(Order)
        .options(
            selectinload(Order.variant).selectinload(Variant.product)
        )
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
    proof_file_id: Optional[str] = None,
    target_variant_id: Optional[int] = None
) -> Deposit:
    deposit = Deposit(
        user_id=user_id,
        amount=round(amount, 2),
        utr_number=utr_number,
        proof_file_id=proof_file_id,
        target_variant_id=target_variant_id,
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

async def update_deposit_proof(
    session: AsyncSession,
    deposit_id: int,
    utr_number: Optional[str] = None,
    proof_file_id: Optional[str] = None
) -> Optional[Deposit]:
    deposit = await get_deposit(session, deposit_id)
    if not deposit:
        return None
    if utr_number:
        deposit.utr_number = utr_number
    if proof_file_id:
        deposit.proof_file_id = proof_file_id
    await session.commit()
    await session.refresh(deposit)
    return deposit

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

async def get_all_deposits(session: AsyncSession, limit: int = 50) -> List[Deposit]:
    """Admin: Returns most recent deposits (all statuses) for payment history view."""
    stmt = (
        select(Deposit)
        .order_by(Deposit.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def get_deposits_stats(session: AsyncSession):
    """Returns total captured (SUCCESS+APPROVED) vs pending deposit stats."""
    captured_stmt = select(func.sum(Deposit.amount)).where(Deposit.status.in_(["APPROVED", "SUCCESS"]))
    pending_stmt = select(func.sum(Deposit.amount)).where(Deposit.status == "PENDING")
    count_stmt = select(func.count(Deposit.id))

    cap_res = await session.execute(captured_stmt)
    pend_res = await session.execute(pending_stmt)
    cnt_res = await session.execute(count_stmt)

    return {
        "total_captured": round(cap_res.scalar() or 0.0, 2),
        "total_pending": round(pend_res.scalar() or 0.0, 2),
        "total_count": cnt_res.scalar() or 0
    }



async def seed_initial_data(session: AsyncSession, force: bool = False):
    """
    Seeds initial default categories and products ONLY if the database is completely empty.
    If the database already contains categories created/edited by the admin, this function
    does NOT touch, modify, recreate, or overwrite any categories, products, or emojis.
    """
    from sqlalchemy import func
    existing_count = (await session.execute(select(func.count(Category.id)).where(Category.is_active == True))).scalar() or 0
    if existing_count > 0 and not force:
        return

    # 1. Standardize Categories (Only executed for brand-new fresh database setups)
    cats_data = [
        ("OTT & Streaming", "🍿", 1, CustomEmojis.NETFLIX),
        ("AI Tools & Productivity", "🤖", 2, CustomEmojis.CHATGPT),
        ("VPN Services", "🛡️", 3, CustomEmojis.NORDVPN),
        ("Education & Developer", "🎓", 4, None),
        ("Gaming & Utilities", "🎮", 5, CustomEmojis.TELEGRAM),
        ("Freebies & Deals", "🎁", 6, CustomEmojis.GIFT),
    ]

    # Deduplicate existing duplicate variants across products in database
    all_active_vars = (await session.execute(select(Variant).where(Variant.is_active == True))).scalars().all()
    seen_var_keys = {}
    for v in all_active_vars:
        clean_v_name = clean_button_text(v.name) or v.name
        v.name = clean_v_name
        key = (v.product_id, round(v.price, 2))
        if key in seen_var_keys:
            primary_v = seen_var_keys[key]
            if len(v.name) > len(primary_v.name):
                primary_v.name = v.name
            await session.execute(
                update(Stock).where(Stock.variant_id == v.id).values(variant_id=primary_v.id)
            )
            v.is_active = False
        else:
            seen_var_keys[key] = v
    await session.commit()

    cats_dict = {}
    for name, emoji, order, custom_id in cats_data:
        stmt = select(Category).where(Category.name == name)
        res = await session.execute(stmt)
        cat = res.scalars().first()
        if not cat:
            cat = Category(name=name, emoji=emoji, sort_order=order, custom_emoji_id=custom_id, is_active=True)
            session.add(cat)
            await session.flush()
        else:
            cat.emoji = emoji
            cat.custom_emoji_id = custom_id
            cat.sort_order = order
            cat.is_active = True
            await session.flush()
        cats_dict[name] = cat

    async def ensure_prod(cat_name, title, emoji, desc, variants_list, custom_emoji_id=None):
        cat = cats_dict.get(cat_name)
        if not cat:
            return
        stmt = select(Product).where(Product.title == title, Product.category_id == cat.id)
        res = await session.execute(stmt)
        prod = res.scalars().first()
        if not prod:
            prod = Product(category_id=cat.id, title=title, emoji=emoji, description=desc, custom_emoji_id=custom_emoji_id, is_active=True)
            session.add(prod)
            await session.flush()
        else:
            prod.description = desc
            prod.emoji = emoji
            prod.is_active = True
            if custom_emoji_id:
                prod.custom_emoji_id = custom_emoji_id
            await session.flush()
        
        for var_tuple in variants_list:
            v_name = var_tuple[0]
            v_price = var_tuple[1]
            v_type = var_tuple[2]
            v_spec = var_tuple[3]
            v_fulf = var_tuple[4] if len(var_tuple) > 4 else "AUTOMATIC"
            v_time = var_tuple[5] if len(var_tuple) > 5 else "1–2 Hours"
            v_prompt = var_tuple[6] if len(var_tuple) > 6 else None
            v_req_input = var_tuple[7] if len(var_tuple) > 7 else (True if v_prompt else (v_fulf == "MANUAL" and ("Invite" in v_name or "Family" in v_name)))
            
            v_stmt = select(Variant).where(Variant.product_id == prod.id, Variant.name == v_name)
            v_res = await session.execute(v_stmt)
            existing_v = v_res.scalars().first()
            if not existing_v:
                session.add(Variant(
                    product_id=prod.id,
                    name=v_name,
                    price=v_price,
                    variant_type=v_type,
                    detailed_description=v_spec,
                    fulfillment_type=v_fulf,
                    manual_dispatch_time=v_time,
                    input_prompt=v_prompt,
                    requires_customer_input=v_req_input,
                    is_active=True
                ))
            else:
                existing_v.price = v_price
                existing_v.variant_type = v_type
                existing_v.detailed_description = v_spec
                existing_v.fulfillment_type = v_fulf
                existing_v.manual_dispatch_time = v_time
                existing_v.input_prompt = v_prompt
                existing_v.requires_customer_input = v_req_input
                existing_v.is_active = True

    # --- 1. OTT & Streaming ---
    await ensure_prod(
        "OTT & Streaming", "Netflix Premium 4K UHD", "🍿",
        "Official Netflix Ultra HD 4K streaming accounts with private or shared profiles.",
        [
            ("1 Month Private Profile", 129.0, "Private Profile",
             "✦ <b>Quality:</b> 4K Ultra HD + HDR & Dolby Atmos\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen (Pin Locked)\n"
             "✦ <b>Devices:</b> Smart TV, Mobile, Laptop, Tablet, PC\n"
             "✦ <b>Warranty:</b> 30 Days Replacement Guarantee\n"
             "✦ <b>Rules:</b> Do not change password or email\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("3 Months Private Profile", 359.0, "Private Profile",
             "✦ <b>Quality:</b> 4K Ultra HD + HDR\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen (Your Own Pin)\n"
             "✦ <b>Warranty:</b> 90 Days Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("6 Months Private Profile", 679.0, "Private Profile",
             "✦ <b>Quality:</b> Ultra HD 4K Quality\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen\n"
             "✦ <b>Warranty:</b> 180 Days Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("12 Months Private Profile", 1249.0, "Private Profile",
             "✦ <b>Quality:</b> Ultra HD 4K Quality (1 Year)\n"
             "✦ <b>Screen:</b> 1 Dedicated Pin-locked Profile\n"
             "✦ <b>Warranty:</b> 365 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("1 Month Shared Profile", 99.0, "Shared Profile",
             "✦ <b>Quality:</b> Ultra HD 4K Quality\n"
             "✦ <b>Screen:</b> Shared Profile\n"
             "✦ <b>Warranty:</b> 30 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
        ],
        custom_emoji_id=CustomEmojis.NETFLIX
    )

    await ensure_prod(
        "OTT & Streaming", "Amazon Prime Video", "📦",
        "Amazon Prime Video Premium with 4K UHD HDR streaming.",
        [
            ("1 Month Private Profile", 79.0, "Private Profile",
             "✦ <b>Quality:</b> 4K Ultra HD + HDR\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen (Pin Locked)\n"
             "✦ <b>Devices:</b> Smart TV, Mobile, Laptop, PC\n"
             "✦ <b>Warranty:</b> 30 Days Full Replacement Warranty\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("6 Months Private Profile", 299.0, "Private Profile",
             "✦ <b>Quality:</b> 4K Ultra HD Streaming\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen\n"
             "✦ <b>Warranty:</b> 180 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
            ("12 Months Private Profile", 499.0, "Private Profile",
             "✦ <b>Quality:</b> 4K Ultra HD Streaming\n"
             "✦ <b>Screen:</b> 1 Dedicated Screen\n"
             "✦ <b>Warranty:</b> 365 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Automated Delivery"),
        ],
        custom_emoji_id=CustomEmojis.PRIME
    )

    await ensure_prod(
        "OTT & Streaming", "YouTube Premium", "🔴",
        "Ad-free YouTube & YouTube Music with background playback & downloads.",
        [
            ("1 Month Family Invite", 49.0, "Invite Link",
             "✦ <b>Features:</b> Ad-Free YouTube + YouTube Music\n"
             "✦ <b>Activation:</b> Added to your personal Gmail\n"
             "✦ <b>Warranty:</b> 30 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "📧 Please send your Gmail address for YouTube Family invite activation:"),
            ("12 Months Family Invite", 299.0, "Invite Link",
             "✦ <b>Features:</b> 12 Months Ad-Free YouTube\n"
             "✦ <b>Activation:</b> Added to your personal Gmail\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "📧 Please send your Gmail address for 1 Year YouTube invite activation:"),
        ],
        custom_emoji_id=CustomEmojis.YOUTUBE
    )

    await ensure_prod(
        "OTT & Streaming", "Spotify Premium", "🎵",
        "Spotify Premium individual & family promo codes with high quality lossless audio.",
        [
            ("3 Months Promo Code", 99.0, "Redeem Code",
             "✦ <b>Quality:</b> 320kbps Lossless Audio\n"
             "✦ <b>Features:</b> Ad-free music & unlimited skips\n"
             "✦ <b>Delivery:</b> Instant Redeem Link"),
            ("12 Months Individual", 299.0, "Redeem Code",
             "✦ <b>Features:</b> 1 Year Ad-Free Music\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Activation"),
        ],
        custom_emoji_id=CustomEmojis.SPOTIFY
    )

    await ensure_prod(
        "OTT & Streaming", "Zee5 Premium", "📺",
        "Zee5 4K VIP subscription for all original web series, live TV and regional movies.",
        [
            ("1 Month Private Login", 49.0, "Private Account",
             "✦ <b>Quality:</b> 1080p HD Zee5 Originals\n"
             "✦ <b>Access:</b> Direct Login Details\n"
             "✦ <b>Warranty:</b> 30 Days Replacement\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
            ("12 Months All Access", 249.0, "Private Account",
             "✦ <b>Features:</b> 1 Year Unlimited Zee5 Streaming\n"
             "✦ <b>Warranty:</b> 365 Days Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ],
        custom_emoji_id=CustomEmojis.ZEE5 if hasattr(CustomEmojis, 'ZEE5') else None
    )

    await ensure_prod(
        "OTT & Streaming", "Apple Music", "🍏",
        "Apple Music individual subscription with lossless audio and Spatial Audio.",
        [
            ("3 Months Family Invite", 99.0, "Invite Link",
             "✦ <b>Quality:</b> Lossless 24-bit 192kHz Audio\n"
             "✦ <b>Activation:</b> Added to your Apple ID\n"
             "✦ <b>Warranty:</b> 90 Days Guarantee\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "📧 Please send your Apple ID email:"),
            ("12 Months Family Invite", 349.0, "Invite Link",
             "✦ <b>Features:</b> 1 Year Apple Music Subscription\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "📧 Please send your Apple ID email:"),
        ],
        custom_emoji_id=CustomEmojis.APPLE_MUSIC if hasattr(CustomEmojis, 'APPLE_MUSIC') else None
    )

    await ensure_prod(
        "OTT & Streaming", "Jio Hotstar Super/Premium", "🌟",
        "JioCinema & Disney+ Hotstar 4K HDR live sports and premium originals.",
        [
            ("1 Month Super (2 Screens)", 89.0, "Shared Login",
             "✦ <b>Quality:</b> Full HD 1080p + Live Cricket\n"
             "✦ <b>Access:</b> Mobile + TV / Web\n"
             "✦ <b>Warranty:</b> 30 Days Replacement\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
            ("12 Months Premium (4 Screens 4K)", 499.0, "Private Account",
             "✦ <b>Quality:</b> 4K Ultra HD + Dolby Vision\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ],
        custom_emoji_id=CustomEmojis.HOTSTAR if hasattr(CustomEmojis, 'HOTSTAR') else None
    )

    await ensure_prod(
        "OTT & Streaming", "Crunchyroll Mega Fan", "🍥",
        "Ad-free anime streaming in full HD with offline downloads.",
        [
            ("1 Month Mega Fan", 69.0, "Private Account",
             "✦ <b>Quality:</b> 1080p HD Anime Streaming\n"
             "✦ <b>Features:</b> Simulcast 1 hour after Japan\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
            ("12 Months Mega Fan", 399.0, "Private Account",
             "✦ <b>Quality:</b> 1080p Full Access\n"
             "✦ <b>Warranty:</b> 365 Days Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ],
        custom_emoji_id=CustomEmojis.CRUNCHYROLL
    )

    # --- 2. AI Tools & Productivity ---
    await ensure_prod(
        "AI Tools & Productivity", "ChatGPT Plus (GPT-4o)", "🤖",
        "Official OpenAI ChatGPT Plus subscription with GPT-4o, DALL-E 3 and custom GPTs.",
        [
            ("1 Month Private Account", 499.0, "Private Account",
             "✦ <b>Model:</b> GPT-4o, GPT-4, DALL-E 3, Browsing\n"
             "✦ <b>Access:</b> Dedicated Private Login (Email+Pass)\n"
             "✦ <b>Warranty:</b> 30 Days Full Replacement\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ],
        custom_emoji_id=CustomEmojis.CHATGPT
    )

    await ensure_prod(
        "AI Tools & Productivity", "Claude 3.5 Sonnet Pro", "🧠",
        "Anthropic Claude Pro with 5x usage on Claude 3.5 Sonnet and Artifacts.",
        [
            ("1 Month Private Account", 549.0, "Private Account",
             "✦ <b>Features:</b> Claude 3.5 Sonnet and Opus, Projects\n"
             "✦ <b>Access:</b> Dedicated Private Login\n"
             "✦ <b>Warranty:</b> 30 Days Replacement\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ],
        custom_emoji_id=CustomEmojis.CLAUDE
    )

    await ensure_prod(
        "AI Tools & Productivity", "Canva Pro", "🎨",
        "Unlock 100M+ premium photos, templates, fonts and brand kits on Canva.",
        [
            ("1 Year Team Invite", 99.0, "Invite Link",
             "✦ <b>Features:</b> All Pro Templates, Background Remover, Magic AI\n"
             "✦ <b>Activation:</b> Added to your own existing Canva email\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "📧 Please send your Canva registered email address:"),
            ("Lifetime Pro Access", 199.0, "Invite Link",
             "✦ <b>Features:</b> Unlimited Pro Tools and AI Suite\n"
             "✦ <b>Warranty:</b> Lifetime Guarantee\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "📧 Please send your Canva registered email address:"),
        ],
        custom_emoji_id=CustomEmojis.CANVA
    )

    await ensure_prod(
        "AI Tools & Productivity", "CapCut Pro", "✂️",
        "CapCut Pro video editor with premium AI filters, effects and cloud storage.",
        [
            ("6 Months Private Login", 299.0, "Private Account",
             "✦ <b>Features:</b> Auto Captions, 4K 60FPS Export, AI Tools\n"
             "✦ <b>Devices:</b> PC, Mac, Android, iOS\n"
             "✦ <b>Warranty:</b> 180 Days Full Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
            ("12 Months Private Login", 499.0, "Private Account",
             "✦ <b>Features:</b> 12 Months All Pro Effects and Tools\n"
             "✦ <b>Warranty:</b> 365 Days Warranty\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ],
        custom_emoji_id=CustomEmojis.CAPCUT
    )

    # --- 3. VPN Services ---
    await ensure_prod(
        "VPN Services", "NordVPN Premium", "🌐",
        "High-speed ultra secure VPN with Threat Protection and Meshnet.",
        [
            ("1 Year Premium Account", 199.0, "Private Account",
             "✦ <b>Servers:</b> 6000+ Servers in 110 Countries\n"
             "✦ <b>Features:</b> Double VPN, CyberSec, AdBlock\n"
             "✦ <b>Warranty:</b> 365 Days Replacement Guarantee\n"
             "✦ <b>Delivery:</b> Instant Delivery"),
        ],
        custom_emoji_id=CustomEmojis.NORDVPN
    )

    # --- 4. Education & Developer ---
    await ensure_prod(
        "Education & Developer", "GitHub Copilot Pro", "👨‍💻",
        "AI pair programmer powered by OpenAI and Claude models for code completion.",
        [
            ("1 Year Student/Edu Pack", 299.0, "Activation Link",
             "✦ <b>Features:</b> GitHub Copilot Chat, VS Code & JetBrains integration\n"
             "✦ <b>Warranty:</b> 1 Year Full Warranty\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "📧 Please send your GitHub @username for activation:"),
        ],
        custom_emoji_id=None
    )

    await ensure_prod(
        "Education & Developer", "JetBrains All Products Pack", "⚡",
        "Access to IntelliJ IDEA Ultimate, PyCharm Pro, WebStorm and all JetBrains IDEs.",
        [
            ("1 Year License Key", 399.0, "License Key",
             "✦ <b>Features:</b> Full offline/online activation for all JetBrains IDEs\n"
             "✦ <b>Warranty:</b> 1 Year Guarantee\n"
             "✦ <b>Delivery:</b> Instant Key Delivery"),
        ],
        custom_emoji_id=None
    )

    # --- 5. Gaming & Utilities ---
    await ensure_prod(
        "Gaming & Utilities", "Telegram Premium", "✈️",
        "Official Telegram Premium subscription for 4GB uploads, custom emojis and badges.",
        [
            ("3 Months Gift Code", 499.0, "Gift Link",
             "✦ <b>Features:</b> Custom Emojis, 4GB Uploads, Fast Downloads\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "✈️ Please send your Telegram @username for Premium gift activation:"),
            ("12 Months Gift Code", 1499.0, "Gift Link",
             "✦ <b>Features:</b> 1 Year Full Telegram Premium Perks\n"
             "✦ <b>Delivery:</b> Manual Activation within 1–2 Hours",
             "MANUAL", "1–2 Hours", "✈️ Please send your Telegram @username for 1 Year Premium gift activation:"),
        ],
        custom_emoji_id=CustomEmojis.TELEGRAM
    )

    await ensure_prod(
        "Gaming & Utilities", "Discord Nitro", "💬",
        "Discord Nitro with 2 Server Boosts, HD streaming, custom emojis and stickers.",
        [
            ("1 Month Nitro with 2 Boosts", 149.0, "Gift Link",
             "✦ <b>Features:</b> 2 Server Boosts, 500MB Uploads, HD Stream\n"
             "✦ <b>Delivery:</b> Instant Gift Link"),
        ],
        custom_emoji_id=CustomEmojis.DISCORD
    )

    # --- 6. Freebies & Deals ---
    await ensure_prod(
        "Freebies & Deals", "Discord Nitro Promo Link", "🎁",
        "Free 3-Month Discord Nitro promotion link for eligible accounts.",
        [
            ("Free 3 Months Promo Link", 0.0, "Promo Link",
             "✦ <b>Features:</b> 3 Months Free Nitro Trial\n"
             "✦ <b>Eligibility:</b> Accounts that haven't had Nitro in the past 12 months\n"
             "✦ <b>Delivery:</b> Instant Claim Link"),
        ],
        custom_emoji_id=CustomEmojis.GIFT
    )

    # Clean up empty duplicate products with 0 variants
    prods_stmt = select(Product)
    all_prods = (await session.execute(prods_stmt)).scalars().all()
    for p in all_prods:
        v_count = (await session.execute(select(func.count(Variant.id)).where(Variant.product_id == p.id, Variant.is_active == True))).scalar() or 0
        if v_count == 0:
            p.is_active = False

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
