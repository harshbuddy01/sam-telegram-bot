from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Category, Product, Variant, Order, Deposit
from utils.emojis import Emojis, clean_button_text, CustomEmojis
import config

def get_admin_main_keyboard(pending_deposits: int = 0, pending_orders: int = 0) -> InlineKeyboardMarkup:
    dep_badge = f" ({pending_deposits})" if pending_deposits > 0 else ""
    ord_badge = f" ({pending_orders})" if pending_orders > 0 else ""
    
    buttons = [
        [
            InlineKeyboardButton(text=f"Pending Orders{ord_badge}", callback_data="adm_pending_orders", icon_custom_emoji_id=CustomEmojis.ORDERS),
            InlineKeyboardButton(text=f"Deposits{dep_badge}", callback_data="adm_deposits", icon_custom_emoji_id=CustomEmojis.WALLET)
        ],
        [
            InlineKeyboardButton(text="Inventory & Stock Hub", callback_data="adm_stock", icon_custom_emoji_id=CustomEmojis.KEY),
            InlineKeyboardButton(text="Orders & Sales Logs", callback_data="adm_orders_log", icon_custom_emoji_id=CustomEmojis.ORDERS)
        ],
        [
            InlineKeyboardButton(text="Store Statistics", callback_data="adm_stats", icon_custom_emoji_id=CustomEmojis.TROPHY),
            InlineKeyboardButton(text="User Balance Adjust", callback_data="adm_users", icon_custom_emoji_id=CustomEmojis.VERIFIED)
        ],
        [
            InlineKeyboardButton(text="Manage Categories", callback_data="adm_cats", icon_custom_emoji_id=CustomEmojis.SHOP),
            InlineKeyboardButton(text="Manage Products", callback_data="adm_prods", icon_custom_emoji_id=CustomEmojis.SPARKLE)
        ],
        [
            InlineKeyboardButton(text="Manage Plans & Pricing", callback_data="adm_variants", icon_custom_emoji_id=CustomEmojis.DIAMOND),
            InlineKeyboardButton(text="Broadcast Announcement", callback_data="adm_broadcast", icon_custom_emoji_id=CustomEmojis.FIRE)
        ],
        [
            InlineKeyboardButton(text="🎨 Store Design & Page Customizer", callback_data="adm_customizer", icon_custom_emoji_id=CustomEmojis.SPARKLE)
        ],
        [
            InlineKeyboardButton(text="⚙️ Payment & UPI Settings", callback_data="adm_settings", icon_custom_emoji_id=CustomEmojis.CARD),
            InlineKeyboardButton(text="Exit to Store", callback_data="nav_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_customizer_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🏠 Welcome Screen (/start)", callback_data="adm_tmpl_view_welcome_text", icon_custom_emoji_id=CustomEmojis.CROWN),
            InlineKeyboardButton(text="📁 Categories Header", callback_data="adm_tmpl_view_categories_header", icon_custom_emoji_id=CustomEmojis.SHOP)
        ],
        [
            InlineKeyboardButton(text="📦 Products List Screen", callback_data="adm_tmpl_view_category_products_header", icon_custom_emoji_id=CustomEmojis.SHOP),
            InlineKeyboardButton(text="✨ Product Line Style", callback_data="adm_tmpl_view_product_item_format", icon_custom_emoji_id=CustomEmojis.SPARKLE)
        ],
        [
            InlineKeyboardButton(text="🏷️ Plan Detail Specs Card", callback_data="adm_tmpl_view_variant_detail", icon_custom_emoji_id=CustomEmojis.DIAMOND),
            InlineKeyboardButton(text="⚡ 1-Click Checkout Screen", callback_data="adm_tmpl_view_checkout_text", icon_custom_emoji_id=CustomEmojis.FIRE)
        ],
        [
            InlineKeyboardButton(text="🎉 Order Delivery Receipt", callback_data="adm_tmpl_view_delivery_text", icon_custom_emoji_id=CustomEmojis.ORDERS),
            InlineKeyboardButton(text="👤 Customer Profile", callback_data="adm_tmpl_view_profile_text", icon_custom_emoji_id=CustomEmojis.VERIFIED)
        ],
        [
            InlineKeyboardButton(text="🛟 Support & Help Desk", callback_data="adm_tmpl_view_support_text", icon_custom_emoji_id=CustomEmojis.SUPPORT)
        ],
        [
            InlineKeyboardButton(text="◀️ Back to Admin Panel", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_template_edit_keyboard(key: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✏️ Edit This Message Template", callback_data=f"adm_tmpl_edit_{key}", icon_custom_emoji_id=CustomEmojis.SPARKLE)
        ],
        [
            InlineKeyboardButton(text="🔄 Reset to Default Template", callback_data=f"adm_tmpl_reset_{key}", icon_custom_emoji_id=CustomEmojis.LOCK)
        ],
        [
            InlineKeyboardButton(text="◀️ Back to Customizer", callback_data="adm_customizer", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_settings_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📱 Change UPI ID", callback_data="adm_set_upi_id", icon_custom_emoji_id=CustomEmojis.CARD),
            InlineKeyboardButton(text="👤 Change Payee Name", callback_data="adm_set_upi_name", icon_custom_emoji_id=CustomEmojis.VERIFIED)
        ],
        [
            InlineKeyboardButton(text="⚡ Automated Gateway (Razorpay/Cashfree)", callback_data="adm_gateways", icon_custom_emoji_id=CustomEmojis.FIRE)
        ],
        [
            InlineKeyboardButton(text="🛟 Change Support Handle", callback_data="adm_set_support", icon_custom_emoji_id=CustomEmojis.SUPPORT),
            InlineKeyboardButton(text="◀️ Back to Admin Panel", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_gateway_settings_keyboard(is_rzp_active: bool, is_paypal_active: bool, is_oxapay_active: bool) -> InlineKeyboardMarkup:
    rzp_status = "🟢 Active" if is_rzp_active else "⚪ Not Set"
    pp_status = "🟢 Active" if is_paypal_active else "⚪ Not Set"
    oxa_status = "🟢 Active" if is_oxapay_active else "⚪ Not Set"

    buttons = [
        [
            InlineKeyboardButton(text=f"⚡ Razorpay / UPI ({rzp_status})", callback_data="adm_set_rzp", icon_custom_emoji_id=CustomEmojis.FIRE)
        ],
        [
            InlineKeyboardButton(text=f"🅿️ PayPal & Cards ({pp_status})", callback_data="adm_set_paypal", icon_custom_emoji_id=CustomEmojis.CARD)
        ],
        [
            InlineKeyboardButton(text=f"🪙 OxaPay Crypto ({oxa_status})", callback_data="adm_set_oxapay", icon_custom_emoji_id=CustomEmojis.DIAMOND)
        ],
        [
            InlineKeyboardButton(text="◀️ Back to Settings", callback_data="adm_settings", icon_custom_emoji_id=CustomEmojis.CROWN)
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
                callback_data=f"adm_audit_{o.id}",
                icon_custom_emoji_id=CustomEmojis.ORDERS
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="Back to Admin Panel", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_order_audit_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back to Orders Log", callback_data="adm_orders_log", icon_custom_emoji_id=CustomEmojis.ORDERS)],
        [InlineKeyboardButton(text="Admin Home", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)]
    ])

def get_admin_payments_keyboard(deposits: list) -> InlineKeyboardMarkup:
    buttons = []
    for dep in deposits[:20]:
        status_icon = "🟢" if dep.status in ("APPROVED", "SUCCESS") else ("⏳" if dep.status == "PENDING" else "❌")
        gateway_badge = "Rzp" if dep.gateway == "RAZORPAY" else ("CF" if dep.gateway == "CASHFREE" else "UPI")
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_icon} #{dep.id} • ₹{dep.amount:.0f} • {gateway_badge} • ID:{dep.user_id}",
                callback_data=f"adm_dep_detail_{dep.id}",
                icon_custom_emoji_id=CustomEmojis.WALLET
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="Admin Home", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)



def get_admin_stock_inventory_keyboard(variants: list[Variant], stock_counts: dict[int, int]) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        prod_title = var.product.title if var.product else "Product"
        is_manual = (getattr(var, "fulfillment_type", "AUTOMATIC") == "MANUAL")
        
        if is_manual:
            stock = stock_counts.get(var.id, 0)
            badge = f"⏱️ Manual ({stock})" if stock > 0 else "🔴 Out of Stock"
        else:
            stock = stock_counts.get(var.id, 0)
            badge = f"🟢 {stock}" if stock > 0 else "🔴 0"
            
        buttons.append([
            InlineKeyboardButton(
                text=f"{clean_button_text(prod_title)} ➜ {clean_button_text(var.name)} [{badge}]",
                callback_data=f"adm_stock_manage_{var.id}",
                icon_custom_emoji_id=CustomEmojis.KEY
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="Back to Admin Hub", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_variant_stock_actions_keyboard(variant_id: int, is_manual: bool = False, stock_count: int = 0) -> InlineKeyboardMarkup:
    buttons = []
    if not is_manual:
        buttons.append([
            InlineKeyboardButton(text="Upload Accounts / Stock (Bulk)", callback_data=f"adm_stock_add_{variant_id}", icon_custom_emoji_id=CustomEmojis.KEY)
        ])
        if stock_count > 0:
            buttons.append([
                InlineKeyboardButton(text=f"View Unsold Accounts ({stock_count})", callback_data=f"adm_stock_view_{variant_id}", icon_custom_emoji_id=CustomEmojis.ORDERS),
                InlineKeyboardButton(text="Clear Unsold Stock", callback_data=f"adm_stock_clear_{variant_id}", icon_custom_emoji_id=CustomEmojis.LOCK)
            ])
    else:
        buttons.append([
            InlineKeyboardButton(text=f"✏️ Set Available Slots / Stock ({stock_count})", callback_data=f"adm_stock_setslots_{variant_id}", icon_custom_emoji_id=CustomEmojis.KEY)
        ])
    buttons.append([
        InlineKeyboardButton(text="Back to Stock List", callback_data="adm_stock", icon_custom_emoji_id=CustomEmojis.KEY),
        InlineKeyboardButton(text="Admin Home", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_pending_orders_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    buttons = []
    for o in orders:
        created_str = o.created_at.strftime("%d/%m %H:%M")
        var_name = o.variant.name if o.variant else "Item"
        buttons.append([
            InlineKeyboardButton(
                text=f"#{o.id} • {var_name} ({o.customer_input[:15]}...) - {created_str}",
                callback_data=f"adm_ord_view_{o.id}",
                icon_custom_emoji_id=CustomEmojis.ORDERS
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="Back to Admin Panel", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_manual_order_detail_keyboard(order_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Fulfill & Send Credentials", callback_data=f"adm_man_ful_{order_id}", icon_custom_emoji_id=CustomEmojis.KEY),
            InlineKeyboardButton(text="Cancel & Refund", callback_data=f"adm_man_ref_{order_id}", icon_custom_emoji_id=CustomEmojis.LOCK)
        ],
        [
            InlineKeyboardButton(text="Back to Pending Orders", callback_data="adm_pending_orders", icon_custom_emoji_id=CustomEmojis.ORDERS)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Alias for backward compatibility
get_admin_order_actions_keyboard = get_admin_manual_order_detail_keyboard

def get_admin_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        clean_name = clean_button_text(cat.name)
        btn_kwargs = {
            "text": clean_name,
            "callback_data": f"adm_cat_edit_{cat.id}"
        }
        if cat.custom_emoji_id and str(cat.custom_emoji_id).isdigit():
            btn_kwargs["icon_custom_emoji_id"] = str(cat.custom_emoji_id)
        elif cat.emoji:
            btn_kwargs["text"] = f"{cat.emoji} {clean_name}"

        buttons.append([
            InlineKeyboardButton(**btn_kwargs),
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"adm_cat_edit_{cat.id}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"adm_cat_del_{cat.id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add New Category", callback_data="adm_cat_add", icon_custom_emoji_id=CustomEmojis.SPARKLE)
    ])
    buttons.append([
        InlineKeyboardButton(text="Back to Admin Panel", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_category_edit_keyboard(category_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🏷️ Edit Name & Emojis", callback_data=f"adm_catedit_name_{category_id}", icon_custom_emoji_id=CustomEmojis.SPARKLE),
            InlineKeyboardButton(text="📦 View Products", callback_data=f"adm_selcat_viewprods_{category_id}", icon_custom_emoji_id=CustomEmojis.SHOP)
        ],
        [
            InlineKeyboardButton(text="🗑️ Delete Category", callback_data=f"adm_cat_del_{category_id}", icon_custom_emoji_id=CustomEmojis.LOCK),
            InlineKeyboardButton(text="◀️ Back to Categories", callback_data="adm_cats", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_category_select_keyboard(categories: list[Category], action: str = "addprod") -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        clean_name = clean_button_text(cat.name)
        btn_kwargs = {
            "text": clean_name,
            "callback_data": f"adm_selcat_{action}_{cat.id}"
        }
        if cat.custom_emoji_id and str(cat.custom_emoji_id).isdigit():
            btn_kwargs["icon_custom_emoji_id"] = str(cat.custom_emoji_id)
        elif cat.emoji:
            btn_kwargs["text"] = f"{cat.emoji} {clean_name}"

        buttons.append([
            InlineKeyboardButton(**btn_kwargs)
        ])
    buttons.append([
        InlineKeyboardButton(text="Cancel", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_products_keyboard(products: list[Product], category_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for prod in products:
        clean_title = clean_button_text(prod.title)
        btn_kwargs = {
            "text": clean_title,
            "callback_data": f"adm_prod_edit_{prod.id}"
        }
        if prod.custom_emoji_id and str(prod.custom_emoji_id).isdigit():
            btn_kwargs["icon_custom_emoji_id"] = str(prod.custom_emoji_id)
        elif prod.emoji:
            btn_kwargs["text"] = f"{prod.emoji} {clean_title}"

        buttons.append([
            InlineKeyboardButton(**btn_kwargs),
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"adm_prod_edit_{prod.id}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"adm_prod_del_{prod.id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add Product to this Category", callback_data=f"adm_prod_add_{category_id}", icon_custom_emoji_id=CustomEmojis.SPARKLE)
    ])
    buttons.append([
        InlineKeyboardButton(text="Back to Categories", callback_data="adm_prods", icon_custom_emoji_id=CustomEmojis.SHOP)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_product_edit_keyboard(product_id: int, category_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🏷️ Edit Title & Emojis", callback_data=f"adm_prodedit_title_{product_id}", icon_custom_emoji_id=CustomEmojis.SPARKLE),
            InlineKeyboardButton(text="📝 Edit Description", callback_data=f"adm_prodedit_desc_{product_id}", icon_custom_emoji_id=CustomEmojis.DIAMOND)
        ],
        [
            InlineKeyboardButton(text="✨ Manage Plans & Pricing", callback_data=f"adm_selprod_viewvars_{product_id}", icon_custom_emoji_id=CustomEmojis.KEY),
            InlineKeyboardButton(text="🗑️ Delete Product", callback_data=f"adm_prod_del_{product_id}", icon_custom_emoji_id=CustomEmojis.LOCK)
        ],
        [
            InlineKeyboardButton(text="◀️ Back to Products", callback_data=f"adm_selcat_viewprods_{category_id}", icon_custom_emoji_id=CustomEmojis.SHOP),
            InlineKeyboardButton(text="🏠 Admin Home", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_product_select_keyboard(products: list[Product], action: str = "addvar") -> InlineKeyboardMarkup:
    buttons = []
    for prod in products:
        clean_title = clean_button_text(prod.title)
        buttons.append([
            InlineKeyboardButton(text=f"{clean_title}", callback_data=f"adm_selprod_{action}_{prod.id}", icon_custom_emoji_id=CustomEmojis.SPARKLE)
        ])
    buttons.append([
        InlineKeyboardButton(text="Cancel", callback_data="admin_home", icon_custom_emoji_id=CustomEmojis.CROWN)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_variants_keyboard(variants: list[Variant], product_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for var in variants:
        clean_name = clean_button_text(var.name)
        buttons.append([
            InlineKeyboardButton(text=f"✨ {clean_name} ({config.CURRENCY_SYMBOL}{var.price:.0f})", callback_data=f"adm_var_edit_{var.id}"),
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"adm_var_edit_{var.id}"),
            InlineKeyboardButton(text="🗑️ Delete", callback_data=f"adm_var_del_{var.id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add New Plan/Variant", callback_data=f"adm_var_add_{product_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text=f"{Emojis.BACK} Back to Products", callback_data="adm_variants")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_variant_edit_keyboard(variant_id: int, product_id: int, is_manual: bool = False) -> InlineKeyboardMarkup:
    mode_btn_text = "⚡ Switch to MANUAL Mode" if not is_manual else "⚡ Switch to AUTOMATIC Mode"
    
    buttons = [
        [
            InlineKeyboardButton(text="🏷️ Edit Plan Name", callback_data=f"adm_varedit_name_{variant_id}"),
            InlineKeyboardButton(text="💰 Edit Price", callback_data=f"adm_varedit_price_{variant_id}")
        ],
        [
            InlineKeyboardButton(text="📝 Edit Description", callback_data=f"adm_varedit_desc_{variant_id}"),
            InlineKeyboardButton(text=mode_btn_text, callback_data=f"adm_varedit_togglemode_{variant_id}")
        ]
    ]

    if is_manual:
        buttons.append([
            InlineKeyboardButton(text="⏱️ Edit Dispatch Time", callback_data=f"adm_varedit_dispatch_{variant_id}"),
            InlineKeyboardButton(text="✍️ Edit Customer Prompt", callback_data=f"adm_varedit_prompt_{variant_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="📊 Edit Available Stock / Slots", callback_data=f"adm_varedit_stockqty_{variant_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🔑 Manage Live Stock", callback_data=f"adm_stock_manage_{variant_id}")
        ])

    buttons.append([
        InlineKeyboardButton(text="◀️ Back to Plans", callback_data=f"adm_selprod_viewvars_{product_id}"),
        InlineKeyboardButton(text="🏠 Admin Home", callback_data="admin_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_fulfillment_type_keyboard(cancel_cb: str = "admin_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ 100% Automated Instant Stock (Auto-Deliver)", callback_data="adm_var_ff_AUTOMATIC")],
        [InlineKeyboardButton(text="⏱️ Manual Activation (Ask Customer Email / Phone)", callback_data="adm_var_ff_MANUAL")],
        [InlineKeyboardButton(text=f"{Emojis.CANCEL} Cancel", callback_data=cancel_cb)]
    ])

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
