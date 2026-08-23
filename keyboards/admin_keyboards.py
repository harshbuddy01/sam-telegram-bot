from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Category, Product, Variant, Order, Deposit
from utils.emojis import Emojis, clean_button_text
import config

def get_admin_main_keyboard(pending_deposits: int = 0, pending_orders: int = 0) -> InlineKeyboardMarkup:
    dep_badge = f" ({pending_deposits})" if pending_deposits > 0 else ""
    ord_badge = f" ({pending_orders})" if pending_orders > 0 else ""
    
    buttons = [
        [
            InlineKeyboardButton(text=f"⏳ Pending Orders{ord_badge}", callback_data="adm_pending_orders"),
            InlineKeyboardButton(text=f"💳 Deposits{dep_badge}", callback_data="adm_deposits")
        ],
        [
            InlineKeyboardButton(text="🔑 Inventory & Stock Hub", callback_data="adm_stock"),
            InlineKeyboardButton(text="🧾 Orders & Sales Logs", callback_data="adm_orders_log")
        ],
        [
            InlineKeyboardButton(text="📊 Store Statistics", callback_data="adm_stats"),
            InlineKeyboardButton(text="👤 User Balance Adjust", callback_data="adm_users")
        ],
        [
            InlineKeyboardButton(text="📁 Manage Categories", callback_data="adm_cats"),
            InlineKeyboardButton(text="📦 Manage Products", callback_data="adm_prods")
        ],
        [
            InlineKeyboardButton(text="🏷️ Manage Plans & Pricing", callback_data="adm_variants"),
            InlineKeyboardButton(text="📢 Broadcast Announcement", callback_data="adm_broadcast")
        ],
        [
            InlineKeyboardButton(text="🧹 Wipe/Reset Demo Data", callback_data="adm_reset_confirm"),
            InlineKeyboardButton(text="🏠 Exit to Store", callback_data="nav_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_recent_orders_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    buttons = []
    for o in orders:
        status_icon = "🟢" if o.status == "COMPLETED" else ("⏳" if o.status == "PENDING_DISPATCH" else "❌")
        var_name = o.variant.name if o.variant else "Plan"
        user_name = o.user.full_name if o.user else f"User {o.user_id}"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_icon} #{o.id} • {config.CURRENCY_SYMBOL}{o.amount:.0f} • {user_name[:12]}",
                callback_data=f"adm_audit_{o.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Admin Panel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_order_audit_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Back to Orders Log", callback_data="adm_orders_log")],
        [InlineKeyboardButton(text="🏠 Admin Home", callback_data="admin_home")]
    ])

def get_admin_stock_inventory_keyboard(variants: list[Variant], stock_counts: dict[int, int]) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        prod_title = var.product.title if var.product else "Product"
        is_manual = (getattr(var, "fulfillment_type", "AUTOMATIC") == "MANUAL")
        
        if is_manual:
            badge = "⏱️ Manual Plan"
        else:
            stock = stock_counts.get(var.id, 0)
            badge = f"🟢 {stock} In Stock" if stock > 0 else "🔴 0 In Stock"
            
        buttons.append([
            InlineKeyboardButton(
                text=f"📦 {prod_title} ➜ {var.name} [{badge}]",
                callback_data=f"adm_stock_manage_{var.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Admin Hub", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_variant_stock_actions_keyboard(variant_id: int, is_manual: bool = False, stock_count: int = 0) -> InlineKeyboardMarkup:
    buttons = []
    if not is_manual:
        buttons.append([
            InlineKeyboardButton(text="➕ Upload Accounts / Stock (Bulk)", callback_data=f"adm_stock_add_{variant_id}")
        ])
        if stock_count > 0:
            buttons.append([
                InlineKeyboardButton(text=f"👁️ View Unsold Accounts ({stock_count})", callback_data=f"adm_stock_view_{variant_id}"),
                InlineKeyboardButton(text="🗑️ Clear Unsold Stock", callback_data=f"adm_stock_clear_{variant_id}")
            ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Back to Stock List", callback_data="adm_stock"),
        InlineKeyboardButton(text="🏠 Admin Home", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_pending_orders_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    buttons = []
    for o in orders:
        created_str = o.created_at.strftime("%d/%m %H:%M")
        var_name = o.variant.name if o.variant else "Item"
        buttons.append([
            InlineKeyboardButton(
                text=f"⏳ #{o.id} • {var_name} ({o.customer_input[:15]}...) - {created_str}",
                callback_data=f"adm_ord_view_{o.id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Admin Panel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_manual_order_detail_keyboard(order_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🔑 Fulfill & Send Credentials", callback_data=f"adm_man_ful_{order_id}"),
            InlineKeyboardButton(text="❌ Cancel & Refund", callback_data=f"adm_man_ref_{order_id}")
        ],
        [
            InlineKeyboardButton(text="◀️ Back to Pending Orders", callback_data="adm_pending_orders")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        clean_name = clean_button_text(cat.name)
        buttons.append([
            InlineKeyboardButton(text=f"{cat.emoji} {clean_name}", callback_data=f"adm_cat_view_{cat.id}"),
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
        clean_name = clean_button_text(cat.name)
        buttons.append([
            InlineKeyboardButton(text=f"{cat.emoji} {clean_name}", callback_data=f"adm_selcat_{action}_{cat.id}")
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.CANCEL} Cancel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_products_keyboard(products: list[Product], category_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for prod in products:
        clean_title = clean_button_text(prod.title)
        buttons.append([
            InlineKeyboardButton(text=f"{prod.emoji} {clean_title}", callback_data=f"adm_prod_view_{prod.id}"),
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
        clean_title = clean_button_text(prod.title)
        buttons.append([
            InlineKeyboardButton(text=f"{prod.emoji} {clean_title}", callback_data=f"adm_selprod_{action}_{prod.id}")
        ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.CANCEL} Cancel", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_variants_keyboard(variants: list[Variant], product_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        clean_name = clean_button_text(var.name)
        buttons.append([
            InlineKeyboardButton(text=f"✨ {clean_name} ({config.CURRENCY_SYMBOL}{var.price:.0f})", callback_data=f"adm_var_view_{var.id}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"adm_var_del_{var.id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add New Plan/Variant", callback_data=f"adm_var_add_{product_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Products", callback_data="adm_variants")
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
