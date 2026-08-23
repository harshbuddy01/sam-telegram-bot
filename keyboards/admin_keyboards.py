from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Category, Product, Variant
from utils.emojis import Emojis
import config

def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📊 Store Statistics", callback_data="adm_stats"),
            InlineKeyboardButton(text="💳 Pending Deposits", callback_data="adm_deposits")
        ],
        [
            InlineKeyboardButton(text="📁 Manage Categories", callback_data="adm_cats"),
            InlineKeyboardButton(text="📦 Manage Products", callback_data="adm_prods")
        ],
        [
            InlineKeyboardButton(text="🏷️ Manage Plans/Variants", callback_data="adm_variants"),
            InlineKeyboardButton(text="🔑 Upload Stock (Bulk)", callback_data="adm_stock")
        ],
        [
            InlineKeyboardButton(text="📢 Broadcast Announcement", callback_data="adm_broadcast"),
            InlineKeyboardButton(text="👤 User Balance Adjust", callback_data="adm_users")
        ],
        [
            InlineKeyboardButton(text="🧹 Wipe/Reset Demo Data", callback_data="adm_reset_confirm"),
            InlineKeyboardButton(text="🏠 Exit to Store", callback_data="nav_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        buttons.append([
            InlineKeyboardButton(text=f"{cat.emoji} {cat.name}", callback_data=f"adm_cat_view_{cat.id}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"adm_cat_del_{cat.id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add New Category", callback_data="adm_cat_add")
    ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Admin Panel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_category_select_keyboard(categories: list[Category], action: str = "addprod") -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        buttons.append([
            InlineKeyboardButton(text=f"{cat.emoji} {cat.name}", callback_data=f"adm_selcat_{action}_{cat.id}")
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.CANCEL} Cancel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_products_keyboard(products: list[Product], category_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for prod in products:
        buttons.append([
            InlineKeyboardButton(text=f"{prod.emoji} {prod.title}", callback_data=f"adm_prod_view_{prod.id}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"adm_prod_del_{prod.id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add Product to this Category", callback_data=f"adm_prod_add_{category_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Categories", callback_data="adm_prods")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_product_select_keyboard(products: list[Product], action: str = "addvar") -> InlineKeyboardMarkup:
    buttons = []
    for prod in products:
        buttons.append([
            InlineKeyboardButton(text=f"{prod.emoji} {prod.title}", callback_data=f"adm_selprod_{action}_{prod.id}")
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.CANCEL} Cancel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_variants_keyboard(variants: list[Variant], product_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        buttons.append([
            InlineKeyboardButton(text=f"✨ {var.name} ({config.CURRENCY_SYMBOL}{var.price})", callback_data=f"adm_var_view_{var.id}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"adm_var_del_{var.id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add New Plan/Variant", callback_data=f"adm_var_add_{product_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Products", callback_data="adm_variants")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_stock_variant_select_keyboard(variants: list[Variant]) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        prod_title = var.product.title if var.product else "Product"
        buttons.append([
            InlineKeyboardButton(
                text=f"📦 {prod_title} ➜ {var.name}",
                callback_data=f"adm_stock_select_{var.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.CANCEL} Cancel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_deposit_approval_keyboard(deposit_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Approve Deposit", callback_data=f"adm_dep_appr_{deposit_id}"),
            InlineKeyboardButton(text="❌ Reject Deposit", callback_data=f"adm_dep_rej_{deposit_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_cancel_keyboard(callback_data: str = "admin_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{Emojis.CANCEL} Cancel & Return", callback_data=callback_data)]
    ])
