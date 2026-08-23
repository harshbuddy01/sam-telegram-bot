from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Category, Product, Variant, Order
from utils.emojis import Emojis, format_emoji
import config

def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"{Emojis.SHOP} Shop / Browse", callback_data="nav_shop")
        ],
        [
            InlineKeyboardButton(text=f"{Emojis.WALLET} Deposit Funds", callback_data="nav_deposit"),
            InlineKeyboardButton(text=f"{Emojis.PROFILE} My Profile", callback_data="nav_profile")
        ],
        [
            InlineKeyboardButton(text=f"{Emojis.SUPPORT} Support & FAQ", callback_data="nav_support"),
            InlineKeyboardButton(text=f"{Emojis.REFER} Refer & Earn", callback_data="nav_refer")
        ]
    ]

    if config.CHANNEL_LINK or config.GROUP_LINK:
        social_row = []
        if config.CHANNEL_LINK:
            social_row.append(InlineKeyboardButton(text="📢 Channel", url=config.CHANNEL_LINK))
        if config.GROUP_LINK:
            social_row.append(InlineKeyboardButton(text="💬 Group", url=config.GROUP_LINK))
        buttons.append(social_row)

    if is_admin:
        buttons.append([
            InlineKeyboardButton(text=f"{Emojis.ADMIN} Admin Panel", callback_data="admin_home")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    buttons = []
    # Display full-width buttons for clean scannability matching modern design
    for idx, cat in enumerate(categories, 1):
        emoji_icon = cat.emoji or Emojis.CATEGORY
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji_icon} {idx}. {cat.name}",
                callback_data=f"cat_{cat.id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Main Menu", callback_data="nav_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_products_keyboard(
    products: list[Product],
    category_id: int,
    stock_counts: dict[int, int],
    page: int = 1,
    per_page: int = 8
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(products) + per_page - 1) // per_page)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_products = products[start_idx:end_idx]

    buttons = []
    for prod in page_products:
        stock = stock_counts.get(prod.id, 0)
        stock_text = f"{stock} Available" if stock > 0 else "Out of Stock"
        icon = prod.emoji or Emojis.PRODUCT
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {prod.title} {Emojis.DOT} {stock_text}",
                callback_data=f"prod_{prod.id}"
            )
        ])

    # Pagination controls if multiple pages
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"prodpage_{category_id}_{page-1}"))
        nav_row.append(InlineKeyboardButton(text=f"Page {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"prodpage_{category_id}_{page+1}"))
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Go Back", callback_data="nav_shop")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_variants_keyboard(
    variants: list[Variant],
    product_id: int,
    category_id: int
) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        price_tag = f"{config.CURRENCY_SYMBOL}{var.price:.1f}"
        buttons.append([
            InlineKeyboardButton(
                text=f"✨ {var.name} {Emojis.DOT} {price_tag}",
                callback_data=f"var_{var.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Go Back", callback_data=f"cat_{category_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_product_detail_keyboard(
    variant_id: int,
    price: float,
    product_id: int,
    has_stock: bool
) -> InlineKeyboardMarkup:
    buttons = []
    if has_stock:
        buttons.append([
            InlineKeyboardButton(
                text=f"{Emojis.WALLET} Buy Now ({config.CURRENCY_SYMBOL}{price:.2f})",
                callback_data=f"buy_{variant_id}"
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="❌ Out of Stock",
                callback_data="noop"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Plans", callback_data=f"prod_{product_id}"),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deposit_preset_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"➕ {config.CURRENCY_SYMBOL}50", callback_data="depamt_50"),
            InlineKeyboardButton(text=f"➕ {config.CURRENCY_SYMBOL}100", callback_data="depamt_100"),
            InlineKeyboardButton(text=f"➕ {config.CURRENCY_SYMBOL}200", callback_data="depamt_200"),
        ],
        [
            InlineKeyboardButton(text=f"➕ {config.CURRENCY_SYMBOL}500", callback_data="depamt_500"),
            InlineKeyboardButton(text=f"➕ {config.CURRENCY_SYMBOL}1000", callback_data="depamt_1000"),
            InlineKeyboardButton(text=f"➕ {config.CURRENCY_SYMBOL}2000", callback_data="depamt_2000"),
        ],
        [
            InlineKeyboardButton(text="✍️ Enter Custom Amount", callback_data="depamt_custom")
        ],
        [
            InlineKeyboardButton(text=f"{Emojis.BACK} Back to Main Menu", callback_data="nav_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deposit_verification_keyboard(deposit_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📸 Submit UTR / Payment Proof", callback_data=f"submitproof_{deposit_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Cancel Deposit", callback_data="nav_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"{Emojis.ORDERS} Order History", callback_data="view_orders"),
            InlineKeyboardButton(text=f"{Emojis.WALLET} Add Balance", callback_data="nav_deposit")
        ],
        [
            InlineKeyboardButton(text=f"{Emojis.REFER} Referral Link", callback_data="nav_refer"),
            InlineKeyboardButton(text=f"{Emojis.SUPPORT} Need Help?", callback_data="nav_support")
        ],
        [
            InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_orders_list_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    buttons = []
    for order in orders:
        created_str = order.created_at.strftime("%d/%m %H:%M")
        buttons.append([
            InlineKeyboardButton(
                text=f"📜 Order #{order.id} {Emojis.DOT} {config.CURRENCY_SYMBOL}{order.amount} ({created_str})",
                callback_data=f"orderdetail_{order.id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Profile", callback_data="nav_profile"),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_button(callback_data: str = "nav_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{Emojis.BACK} Go Back", callback_data=callback_data)]
    ])
