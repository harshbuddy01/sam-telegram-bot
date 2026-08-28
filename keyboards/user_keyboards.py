from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database.models import Category, Product, Variant, Order
from utils.emojis import Emojis, UI, CustomEmojis, clean_button_text
import config

def get_persistent_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Persistent bottom menu keyboard shown at bottom of user chat on mobile/desktop.
    Matches the layout shown in screenshot with icon_custom_emoji_id.
    """
    buttons = [
        [KeyboardButton(text="Shop", icon_custom_emoji_id=CustomEmojis.SHOP)],
        [
            KeyboardButton(text="Deposit", icon_custom_emoji_id=CustomEmojis.WALLET),
            KeyboardButton(text="My Profile", icon_custom_emoji_id=CustomEmojis.VERIFIED)
        ],
        [
            KeyboardButton(text="Support", icon_custom_emoji_id=CustomEmojis.SUPPORT),
            KeyboardButton(text="Refer & Earn", icon_custom_emoji_id=CustomEmojis.STAR)
        ]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="⚡ Switch to Admin View")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, is_persistent=True)

def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Explore Store", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP),
            InlineKeyboardButton(text="Search Product", callback_data="nav_search", icon_custom_emoji_id=CustomEmojis.SEARCH)
        ],
        [
            InlineKeyboardButton(text="Deposit Wallet", callback_data="nav_deposit", icon_custom_emoji_id=CustomEmojis.WALLET),
            InlineKeyboardButton(text="Order History", callback_data="view_orders", icon_custom_emoji_id=CustomEmojis.ORDERS)
        ],
        [
            InlineKeyboardButton(text="My Account", callback_data="nav_profile", icon_custom_emoji_id=CustomEmojis.VERIFIED),
            InlineKeyboardButton(text="Invite Users", callback_data="nav_refer", icon_custom_emoji_id=CustomEmojis.GIFT)
        ],
        [
            InlineKeyboardButton(text="How to Use", callback_data="nav_guide", icon_custom_emoji_id=CustomEmojis.DIAMOND),
            InlineKeyboardButton(text="Help & Support", callback_data="nav_support", icon_custom_emoji_id=CustomEmojis.SUPPORT)
        ]
    ]

    if config.CHANNEL_LINK or config.GROUP_LINK:
        social_row = []
        if config.CHANNEL_LINK:
            social_row.append(InlineKeyboardButton(text="Official Channel", url=config.CHANNEL_LINK, icon_custom_emoji_id=CustomEmojis.FIRE))
        if config.GROUP_LINK:
            social_row.append(InlineKeyboardButton(text="Community Group", url=config.GROUP_LINK, icon_custom_emoji_id=CustomEmojis.SUPPORT))
        buttons.append(social_row)

    if is_admin:
        buttons.append([
            InlineKeyboardButton(text="ADMIN CONTROL PANEL", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_search_results_keyboard(
    products: list[Product],
    stock_counts: dict[int, int]
) -> InlineKeyboardMarkup:
    buttons = []
    for prod in products:
        stock = stock_counts.get(prod.id, 0)
        stock_badge = f"({stock})" if stock > 0 else "(Out)"
        clean_title = clean_button_text(prod.title)

        if prod.custom_emoji_id and str(prod.custom_emoji_id).isdigit():
            btn_kwargs = {
                "text": f"{clean_title} {stock_badge}",
                "callback_data": f"prod_{prod.id}",
                "icon_custom_emoji_id": str(prod.custom_emoji_id)
            }
        else:
            display_emoji = prod.emoji or "📦"
            btn_kwargs = {
                "text": f"{display_emoji} {clean_title} {stock_badge}",
                "callback_data": f"prod_{prod.id}"
            }

        buttons.append([InlineKeyboardButton(**btn_kwargs)])
    
    buttons.append([
        InlineKeyboardButton(text="Search Another Item", callback_data="nav_search", icon_custom_emoji_id=CustomEmojis.SEARCH),
        InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    buttons = []
    for idx, cat in enumerate(categories, 1):
        clean_name = clean_button_text(cat.name)

        if cat.custom_emoji_id and str(cat.custom_emoji_id).isdigit():
            btn_kwargs = {
                "text": clean_name,
                "callback_data": f"cat_{cat.id}",
                "icon_custom_emoji_id": str(cat.custom_emoji_id)
            }
        else:
            display_emoji = cat.emoji or "📁"
            btn_kwargs = {
                "text": f"{display_emoji}  {clean_name}",
                "callback_data": f"cat_{cat.id}"
            }

        buttons.append([InlineKeyboardButton(**btn_kwargs)])
    
    buttons.append([
        InlineKeyboardButton(text="Search Products", callback_data="nav_search", icon_custom_emoji_id=CustomEmojis.SEARCH),
        InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_products_keyboard(
    products: list[Product],
    category_id: int,
    stock_counts: dict[int, int],
    page: int = 1,
    per_page: int = 6
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(products) + per_page - 1) // per_page)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_products = products[start_idx:end_idx]

    buttons = []
    for prod in page_products:
        stock = stock_counts.get(prod.id, 0)
        stock_indicator = f"({stock})" if stock > 0 else "(Out)"
        clean_title = clean_button_text(prod.title)

        if prod.custom_emoji_id and str(prod.custom_emoji_id).isdigit():
            btn_kwargs = {
                "text": f"{clean_title} {stock_indicator}",
                "callback_data": f"prod_{prod.id}",
                "icon_custom_emoji_id": str(prod.custom_emoji_id)
            }
        else:
            display_emoji = prod.emoji or "📦"
            btn_kwargs = {
                "text": f"{display_emoji} {clean_title} {stock_indicator}",
                "callback_data": f"prod_{prod.id}"
            }

        buttons.append([InlineKeyboardButton(**btn_kwargs)])

    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="Previous", callback_data=f"prodpage_{category_id}_{page-1}", icon_custom_emoji_id=CustomEmojis.LOCK))
        nav_row.append(InlineKeyboardButton(text=f"Page {page} / {total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="Next", callback_data=f"prodpage_{category_id}_{page+1}", icon_custom_emoji_id=CustomEmojis.FIRE))
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="Back to Categories", callback_data="nav_shop", icon_custom_emoji_id=CustomEmojis.SHOP),
        InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_variants_keyboard(
    variants: list[Variant],
    product_id: int,
    category_id: int,
    usd_prices: dict = None  # {variant_id: (usdt_amount, paypal_usd)} optional
) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        clean_name = clean_button_text(var.name)
        inr_tag = f"{config.CURRENCY_SYMBOL}{var.price:.0f}"

        # Build dual pricing label if USD prices available
        if usd_prices and var.id in usd_prices:
            usdt, pp_usd = usd_prices[var.id]
            # Show the lower (crypto) USD price to attract — PayPal shown at checkout
            price_tag = f"{inr_tag}  ·  ~${usdt:.2f} USDT"
        else:
            price_tag = inr_tag

        buttons.append([
            InlineKeyboardButton(
                text=f"{clean_name}  ➜  {price_tag}",
                callback_data=f"var_{var.id}",
                icon_custom_emoji_id=CustomEmojis.SPARKLE
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="Back to Products", callback_data=f"cat_{category_id}", icon_custom_emoji_id=CustomEmojis.SHOP),
        InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_product_detail_keyboard(
    variant_id: int,
    price: float,
    product_id: int,
    has_stock: bool,
    is_manual: bool = False,
    is_admin: bool = False,
    quantity: int = 1
) -> InlineKeyboardMarkup:
    buttons = []
    qty = max(1, min(int(quantity), 10))
    total_price = round(price * qty, 2)

    # Quantity selector row (1–5)
    qty_row = []
    for q in range(1, 6):
        label = f"✅ {q}" if q == qty else str(q)
        qty_row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"setqty_{variant_id}_{q}"
            )
        )
    buttons.append(qty_row)

    # Buy button — show total if qty > 1
    if qty > 1:
        total_label = f"{config.CURRENCY_SYMBOL}{price:.0f} × {qty} = {config.CURRENCY_SYMBOL}{total_price:.2f}"
    else:
        total_label = f"{config.CURRENCY_SYMBOL}{price:.2f}"

    if is_manual:
        buttons.append([
            InlineKeyboardButton(
                text=f"ORDER ACTIVATION  ({total_label})",
                callback_data=f"buy_{variant_id}",
                icon_custom_emoji_id=CustomEmojis.FIRE
            )
        ])
    elif has_stock:
        buttons.append([
            InlineKeyboardButton(
                text=f"PURCHASE NOW  ({total_label})",
                callback_data=f"buy_{variant_id}",
                icon_custom_emoji_id=CustomEmojis.FIRE
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="Currently Out of Stock",
                callback_data="noop",
                icon_custom_emoji_id=CustomEmojis.LOCK
            )
        ])

    if is_admin:
        buttons.append([
            InlineKeyboardButton(
                text="Admin: Upload Accounts to Stock",
                callback_data=f"adm_stock_add_{variant_id}",
                icon_custom_emoji_id=CustomEmojis.KEY
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="Deposit Funds", callback_data="nav_deposit", icon_custom_emoji_id=CustomEmojis.WALLET),
        InlineKeyboardButton(text="Back to Plans", callback_data=f"prod_{product_id}", icon_custom_emoji_id=CustomEmojis.SPARKLE)
    ])
    buttons.append([
        InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deposit_preset_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"{config.CURRENCY_SYMBOL}50", callback_data="depamt_50", icon_custom_emoji_id=CustomEmojis.DIAMOND),
            InlineKeyboardButton(text=f"{config.CURRENCY_SYMBOL}100", callback_data="depamt_100", icon_custom_emoji_id=CustomEmojis.DIAMOND),
            InlineKeyboardButton(text=f"{config.CURRENCY_SYMBOL}200", callback_data="depamt_200", icon_custom_emoji_id=CustomEmojis.DIAMOND),
        ],
        [
            InlineKeyboardButton(text=f"{config.CURRENCY_SYMBOL}500", callback_data="depamt_500", icon_custom_emoji_id=CustomEmojis.FIRE),
            InlineKeyboardButton(text=f"{config.CURRENCY_SYMBOL}1,000", callback_data="depamt_1000", icon_custom_emoji_id=CustomEmojis.FIRE),
            InlineKeyboardButton(text=f"{config.CURRENCY_SYMBOL}2,000", callback_data="depamt_2000", icon_custom_emoji_id=CustomEmojis.CROWN),
        ],
        [
            InlineKeyboardButton(text="Enter Custom Amount", callback_data="depamt_custom", icon_custom_emoji_id=CustomEmojis.SPARKLE)
        ],
        [
            InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deposit_verification_keyboard(deposit_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Submit UTR / Screenshot", callback_data=f"submitproof_{deposit_id}", icon_custom_emoji_id=CustomEmojis.CHECK)
        ],
        [
            InlineKeyboardButton(text="Cancel Deposit", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="My Order History", callback_data="view_orders", icon_custom_emoji_id=CustomEmojis.ORDERS),
            InlineKeyboardButton(text="Add Funds / Top-Up", callback_data="nav_deposit", icon_custom_emoji_id=CustomEmojis.WALLET)
        ],
        [
            InlineKeyboardButton(text="Referral Link", callback_data="nav_refer", icon_custom_emoji_id=CustomEmojis.GIFT),
            InlineKeyboardButton(text="Contact Support", callback_data="nav_support", icon_custom_emoji_id=CustomEmojis.SUPPORT)
        ],
        [
            InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_orders_list_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    buttons = []
    for order in orders:
        created_str = order.created_at.strftime("%d/%m")
        status = getattr(order, "status", "COMPLETED")
        badge = "🟢" if status == "COMPLETED" else ("⏳" if status == "PENDING_DISPATCH" else "❌")
        
        # Format clean product title
        prod_title = "Item"
        if order.variant and order.variant.product:
            raw_title = clean_button_text(order.variant.product.title)
            prod_title = raw_title.replace("Premium", "").replace("Subscription", "").strip()
            if len(prod_title) > 16:
                prod_title = prod_title[:15] + "…"
        elif order.variant:
            prod_title = clean_button_text(order.variant.name)[:14]

        btn_text = f"{badge} #{order.id} • {prod_title} • {config.CURRENCY_SYMBOL}{order.amount:.0f} ({created_str})"

        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"orderdetail_{order.id}",
                icon_custom_emoji_id=CustomEmojis.ORDERS
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="Back to Profile", callback_data="nav_profile", icon_custom_emoji_id=CustomEmojis.VERIFIED),
        InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_order_detail_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Buttons displayed on the order detail receipt screen."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Need Help / Report Issue", callback_data=f"need_help_{order_id}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
        [InlineKeyboardButton(text="Back to Order History", callback_data="view_orders", icon_custom_emoji_id=CustomEmojis.ORDERS)],
        [InlineKeyboardButton(text="Main Menu", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])

def get_back_button(callback_data: str = "nav_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Go Back", callback_data=callback_data, icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])

def get_post_delivery_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Buttons shown after successful product delivery — I Got It / Need Help."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="I Got It!", callback_data=f"confirm_got_{order_id}", icon_custom_emoji_id=CustomEmojis.CHECK)],
        [InlineKeyboardButton(text="I Need Help", callback_data=f"need_help_{order_id}", icon_custom_emoji_id=CustomEmojis.SUPPORT)],
        [InlineKeyboardButton(text="View in Order History", callback_data="view_orders", icon_custom_emoji_id=CustomEmojis.ORDERS)]
    ])
