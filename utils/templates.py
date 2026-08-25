import os
import re
import datetime
from typing import Dict, Any, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import BotTemplate
from utils.emojis import CustomEmojis, ce, UI, format_emoji, Emojis
import config

# In-memory fast cache for instantaneous template lookups
_TEMPLATE_CACHE: Dict[str, str] = {}

# Default Store Templates (Rich, Premium, and Fully Configurable)
DEFAULT_TEMPLATES: Dict[str, str] = {
    "welcome_text": (
        f"{ce(CustomEmojis.CROWN, '👑')} <b>PREMIUM DIGITAL STORE</b> {ce(CustomEmojis.CROWN, '👑')}\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.SPARKLE, '👋')} Welcome to <b>{{store_name}}</b>!\n"
        f"Your #1 trusted marketplace for instant, verified & guaranteed digital subscriptions.\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.DIAMOND, '💎')} <b>What We Provide:</b>\n"
        f"• {ce(CustomEmojis.SHOP, '🍿')} <b>OTT & Streaming:</b> Netflix, Prime, YouTube, Hotstar\n"
        f"• {ce(CustomEmojis.SPARKLE, '🤖')} <b>AI Tools:</b> ChatGPT Plus, Claude Pro, Canva Pro\n"
        f"• {ce(CustomEmojis.WARRANTY, '🛡️')} <b>VPN & Security:</b> High-Speed VPNs, Discord Nitro\n"
        f"• {ce(CustomEmojis.TROPHY, '🎓')} <b>Developer Tools:</b> GitHub, JetBrains, Premium Keys"
        f"</blockquote>\n\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Instant Automated Delivery</b> • {ce(CustomEmojis.WARRANTY, '🛡️')} <b>Full Warranty</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.SPARKLE, '👇')} <i>Choose an option below to start browsing:</i>"
    ),

    "categories_header": (
        f"{ce(CustomEmojis.SHOP, '🛍️')} <b>STORE CATALOG & CATEGORIES</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"All products are <b>100% genuine</b>, covered by full warranty, and delivered instantly upon payment."
        f"</blockquote>\n\n"
        f"<i>Choose a category below to explore:</i>"
    ),

    "category_products_header": (
        f"{{cat_header}}\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>Available Products:</b>\n"
        f"{{product_list}}\n\n"
        f"<i>Select an item below to view plans and pricing:</i>"
    ),

    "product_item_format": (
        f"• {{prod_icon}} <b>{{product_title}}</b> — <i>{{stock_badge}}</i>"
    ),

    "variant_detail": (
        f"{{prod_header}}\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Price:</b> <b>{{currency}}{{price}}</b>\n"
        f"{ce(CustomEmojis.DIAMOND, '🏷️')} <b>Plan:</b> {{variant_name}}\n"
        f"{ce(CustomEmojis.FIRE, '🚀')} <b>Type:</b> {{variant_type}}\n"
        f"{ce(CustomEmojis.TROPHY, '📊')} <b>Stock:</b> {{stock_badge}}\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Warranty:</b> 100% Replacement Guarantee\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Delivery:</b> {{delivery_time}}"
        f"</blockquote>\n\n"
        f"{{description_block}}"
    ),

    "checkout_text": (
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>DIRECT 1-CLICK INSTANT CHECKOUT</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> {{prod_icon}} <b>{{prod_title}}</b>\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{{variant_name}}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Total Amount:</b> <b>{{currency}}{{price}}</b>\n"
        f"{ce(CustomEmojis.FIRE, '⚡')} <b>Delivery:</b> Instant Auto-Delivery upon payment\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.CARD, '📱')} <b>Supported:</b> PhonePe, Google Pay, Paytm, BHIM, CRED, Cards & PayPal"
        f"</blockquote>\n\n"
        f"{ce(CustomEmojis.SPARKLE, '👇')} <i>Scan QR code above with PhonePe/GPay OR click the button below to pay:</i>"
    ),

    "delivery_text": (
        f"{ce(CustomEmojis.SPARKLE, '🎉')} <b>PAYMENT CONFIRMED & ORDER DELIVERED!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.ORDERS, '🧾')} <b>Order ID:</b> #{{order_id}}\n"
        f"{ce(CustomEmojis.SHOP, '📦')} <b>Product:</b> <b>{{prod_title}}</b>\n"
        f"{ce(CustomEmojis.SPARKLE, '✨')} <b>Plan:</b> <b>{{variant_name}}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Amount Paid:</b> <b>{{currency}}{{price}}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CustomEmojis.KEY, '🔑')} <b>YOUR DELIVERED ACCOUNT / CODE:</b>\n"
        f"<i>(Tap the box below to copy automatically)</i>\n\n"
        f"<pre><code>{{delivered_content}}</code></pre>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Full Warranty:</b> Covered throughout validity!\n"
        f"{ce(CustomEmojis.HEART, '❤️')} <i>Thank you for shopping with {{store_name}}!</i>"
    ),

    "profile_text": (
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>CUSTOMER DASHBOARD</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.VERIFIED, '👤')} <b>Name:</b> <b>{{user_name}}</b>\n"
        f"{ce(CustomEmojis.KEY, '🆔')} <b>Telegram ID:</b> <code>{{user_id}}</code>\n"
        f"{ce(CustomEmojis.CARD, '💳')} <b>Wallet Balance:</b> <b>{{currency}}{{balance}}</b>\n"
        f"{ce(CustomEmojis.WALLET, '💰')} <b>Total Spent:</b> <b>{{currency}}{{total_spent}}</b>\n"
        f"{ce(CustomEmojis.ORDERS, '📦')} <b>Total Orders:</b> <b>{{order_count}} completed</b>"
        f"</blockquote>\n\n"
        f"{ce(CustomEmojis.REFER, '🎁')} <b>Referral Rewards:</b>\n"
        f"Invite friends and earn <b>{{referral_percent}}% lifetime cashback</b> on all their purchases!\n\n"
        f"<i>Tap below to deposit funds or view order history:</i>"
    ),

    "support_text": (
        f"{ce(CustomEmojis.SUPPORT, '🛟')} <b>CUSTOMER SUPPORT & HELP CENTER</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"Need assistance with your purchase, custom accounts, or replacements?\n"
        f"Our support team is available 24/7!\n\n"
        f"<blockquote>"
        f"{ce(CustomEmojis.SUPPORT, '💬')} <b>Direct Support:</b> @{{support_username}}\n"
        f"{ce(CustomEmojis.FIRE, '📢')} <b>Official Channel:</b> {{channel_link}}\n"
        f"{ce(CustomEmojis.VERIFIED, '👥')} <b>Community Group:</b> {{group_link}}"
        f"</blockquote>\n\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <b>Warranty Terms:</b>\n"
        f"• All purchases are covered by our replacement guarantee.\n"
        f"• For help or replacements, message our support with your Order ID."
    ),

    "guide_text": (
        f"{ce(CustomEmojis.DIAMOND, '📖')} <b>HOW TO BUY & USE {{store_name}}</b>\n"
        f"{UI.SECTION_BAR}\n\n"
        f"<b>1️⃣ Browse Subscriptions</b>\n"
        f"• Tap <b>'Explore Store'</b> or <b>'Search Product'</b> to browse Netflix, YouTube, Prime, ChatGPT, CapCut, VPNs & developer tools.\n"
        f"• Click on any service to view available plans, durations, and wholesale pricing.\n\n"
        f"<b>2️⃣ Choose Plan & Instant Checkout</b>\n"
        f"• Tap <b>'PURCHASE NOW'</b> on your desired plan.\n"
        f"• Pay instantly with <b>1-Click Checkout</b> via <b>UPI QR Code</b> (GPay / PhonePe / Paytm / CRED), <b>Cards & PayPal</b>, or <b>Crypto (OxaPay)</b>.\n"
        f"• <i>(You can also top up your <b>Wallet</b> anytime for 1-tap balance checkouts.)</i>\n\n"
        f"<b>3️⃣ Instant Automated & Manual Delivery</b>\n"
        f"• {ce(CustomEmojis.FIRE, '⚡')} <b>Instant Stock Items:</b> Your login credentials, password, and screen PIN are delivered directly to this chat in seconds!\n"
        f"• {ce(CustomEmojis.FIRE, '⏱️')} <b>Manual Activation Items:</b> (e.g. YouTube Family Invite, Hotstar, CapCut Pro) Our team activates and dispatches your subscription within 1–2 hours.\n\n"
        f"<b>4️⃣ Order History & 1-Tap Copy</b>\n"
        f"• Tap <b>'Order History'</b> anytime to see all your active subscriptions and receipts.\n"
        f"• Tap the credential box to copy email/password instantly to your clipboard.\n\n"
        f"<b>5️⃣ 100% Replacement Warranty & Support</b>\n"
        f"• Every purchase comes with a 100% replacement warranty covering the full subscription duration.\n"
        f"• Need help? Tap <b>'Need Help?'</b> on your order receipt or contact <b>@{{support_username}}</b>.\n\n"
        f"<b>6️⃣ Invite Friends & Earn Cashback</b>\n"
        f"• Tap <b>'Invite Users'</b> to get your personal referral link.\n"
        f"• Earn <b>{{referral_percent}}% wallet credit</b> on every purchase made by your invited friends!\n"
        f"{UI.SECTION_BAR}\n\n"
        f"{ce(CustomEmojis.WARRANTY, '🛡️')} <i>Fast, reliable, and 100% genuine digital subscriptions.</i>"
    )
}

# Metadata describing each template for the Admin UI
TEMPLATE_METADATA: Dict[str, Dict[str, Any]] = {
    "welcome_text": {
        "title": "🏠 Welcome Screen (/start)",
        "desc": "The main greeting message customers see when opening the bot.",
        "tags": ["{store_name}"]
    },
    "categories_header": {
        "title": "📁 Catalog Categories Header",
        "desc": "Header displayed when browsing the main category list.",
        "tags": ["{store_name}"]
    },
    "category_products_header": {
        "title": "📦 Category Products List Screen",
        "desc": "The message displaying products inside a selected category.",
        "tags": ["{cat_header}", "{category_name}", "{product_list}"]
    },
    "product_item_format": {
        "title": "✨ Product Item Line Style",
        "desc": "How each product row is formatted in the category view.",
        "tags": ["{prod_icon}", "{product_title}", "{stock_badge}"]
    },
    "variant_detail": {
        "title": "🏷️ Plan & Specs Detail Card",
        "desc": "The card showing product details, pricing, specs & warranty.",
        "tags": ["{prod_header}", "{prod_title}", "{prod_icon}", "{variant_name}", "{currency}", "{price}", "{variant_type}", "{fulfillment_badge}", "{stock_badge}", "{description_block}", "{delivery_time}"]
    },
    "checkout_text": {
        "title": "⚡ Direct 1-Click Checkout Screen",
        "desc": "The message displayed with UPI QR code & payment options.",
        "tags": ["{prod_title}", "{prod_icon}", "{variant_name}", "{currency}", "{price}"]
    },
    "delivery_text": {
        "title": "🎉 Order Delivered Confirmation",
        "desc": "The delivery receipt with credentials box & warranty note.",
        "tags": ["{order_id}", "{prod_title}", "{variant_name}", "{currency}", "{price}", "{delivered_content}", "{store_name}"]
    },
    "profile_text": {
        "title": "👤 Customer Profile Dashboard",
        "desc": "The profile view showing balance, spending & referral info.",
        "tags": ["{user_name}", "{user_id}", "{currency}", "{balance}", "{total_spent}", "{order_count}", "{referral_percent}"]
    },
    "support_text": {
        "title": "🛟 Support & Help Desk",
        "desc": "Support contact links and warranty guidelines.",
        "tags": ["{support_username}", "{channel_link}", "{group_link}"]
    },
    "guide_text": {
        "title": "📖 How to Use & Purchase Guide",
        "desc": "The comprehensive buying guide explaining 1-click checkout, delivery, and warranty.",
        "tags": ["{store_name}", "{support_username}", "{referral_percent}"]
    }
}

async def get_template(session: AsyncSession, key: str) -> str:
    """Fetches template from memory cache or database, fallback to default."""
    if key in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[key]

    try:
        stmt = select(BotTemplate).where(BotTemplate.key == key)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        if record and record.content:
            _TEMPLATE_CACHE[key] = record.content
            return record.content
    except Exception:
        pass

    default_val = DEFAULT_TEMPLATES.get(key, "")
    _TEMPLATE_CACHE[key] = default_val
    return default_val

async def set_template(session: AsyncSession, key: str, content: str) -> None:
    """Saves custom template into database and updates cache."""
    clean_content = content.strip()
    _TEMPLATE_CACHE[key] = clean_content

    stmt = select(BotTemplate).where(BotTemplate.key == key)
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()
    if record:
        record.content = clean_content
        record.updated_at = datetime.datetime.utcnow()
    else:
        session.add(BotTemplate(key=key, content=clean_content))
    await session.commit()

async def reset_template(session: AsyncSession, key: str) -> str:
    """Resets template back to default."""
    default_val = DEFAULT_TEMPLATES.get(key, "")
    _TEMPLATE_CACHE[key] = default_val

    await session.execute(delete(BotTemplate).where(BotTemplate.key == key))
    await session.commit()
    return default_val

async def render_template(session: AsyncSession, key: str, **kwargs) -> str:
    """Renders template with provided variable arguments safely using exact tag replacement."""
    template_str = await get_template(session, key)
    rendered = template_str
    for k, v in kwargs.items():
        val = str(v) if v is not None else ""
        rendered = rendered.replace(f"{{{k}}}", val)
    return rendered
