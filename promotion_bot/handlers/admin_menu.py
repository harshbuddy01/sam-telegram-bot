from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from database.crud import get_group_stats, get_setting, get_active_promo_message, get_active_sender_account, get_all_sender_accounts
from core.client import tg_manager
from core.broadcaster import broadcaster
import config

router = Router(name="admin_menu")

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="📢 Multi-Ad Campaigns (Per Number)", callback_data="menu_campaigns")
        ],
        [
            InlineKeyboardButton(text="🧙‍♂️ 🚀 Launch Campaign Wizard", callback_data="start_wizard"),
            InlineKeyboardButton(text="📝 Edit Promo Message", callback_data="menu_promo_msg")
        ],
        [
            InlineKeyboardButton(text="🚀 Broadcast Controls", callback_data="menu_broadcast"),
            InlineKeyboardButton(text="👥 Manage Groups", callback_data="menu_groups")
        ],
        [
            InlineKeyboardButton(text="📱 Switch / Add Number", callback_data="menu_auth"),
            InlineKeyboardButton(text="📊 Reports & Failures", callback_data="menu_reports")
        ],
        [
            InlineKeyboardButton(text="🛡️ Anti-Ban Settings", callback_data="menu_settings"),
            InlineKeyboardButton(text="🔄 Refresh Dashboard", callback_data="refresh_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def build_dashboard_text() -> str:
    async with AsyncSessionLocal() as session:
        stats = await get_group_stats(session)
        is_enabled = await get_setting(session, "broadcast_enabled", "true")
        interval = await get_setting(session, "interval_hours", str(config.DEFAULT_INTERVAL_HOURS))
        promo = await get_active_promo_message(session)
        active_acc = await get_active_sender_account(session)
        all_accounts = await get_all_sender_accounts(session)

    # Sender Account Status
    if active_acc:
        premium_badge = "👑 Premium" if active_acc.is_premium else "Standard"
        sender_info = f"✅ <code>{active_acc.phone}</code> (@{active_acc.username or active_acc.first_name}) — {premium_badge}"
    else:
        sender_info = "❌ <i>No sender connected (Tap 'Switch / Add Number')</i>"

    # Broadcaster Status
    progress = broadcaster.get_progress_status()
    if progress["is_running"]:
        status_badge = f"🚀 <b>RUNNING</b> ({progress['current_index']}/{progress['total_targets']} - {progress['progress_percent']}%)"
        if progress["is_paused"]:
            status_badge = "⏸️ <b>PAUSED</b>"
    else:
        status_badge = "🟢 <b>ACTIVE / SCHEDULED</b>" if is_enabled.lower() == "true" else "🔴 <b>STOPPED / PAUSED</b>"

    text = (
        "🤖 <b>TELEGRAM PROMOTION BOT — CONTROL CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Active Sender Number:</b> {sender_info}\n"
        f"👥 <b>Saved Phone Numbers:</b> <code>{len(all_accounts)} accounts</code>\n"
        f"📡 <b>Broadcast Engine:</b> {status_badge}\n"
        f"⏱️ <b>Repeat Interval:</b> Every {interval} Hours\n\n"
        "👥 <b>Target Groups Database:</b>\n"
        f"• <b>Total Saved Groups:</b> <code>{stats.get('TOTAL', 0)}</code>\n"
        f"• 🟢 Active & Ready: <code>{stats.get('ACTIVE', 0)}</code>\n"
        f"• ⏳ Slowmode Queued: <code>{stats.get('SLOWMODE', 0)}</code>\n"
        f"• 🔴 Banned / Restricted: <code>{stats.get('BANNED', 0) + stats.get('RESTRICTED', 0)}</code>\n"
        f"• ⚠️ Invalid / Expired: <code>{stats.get('INVALID_LINK', 0)}</code>\n\n"
        f"📝 <b>Active Promo Message:</b> {promo.title} ({promo.media_type.upper()})\n"
        "🛡️ <b>Anti-Ban Protection:</b> <code>ACTIVE (18-35s Jitter + Anti-Hash Spintax)</code>\n\n"
        "<i>Tap <b>'Launch Campaign Wizard'</b> for step-by-step setup or choose a menu option below:</i>"
    )
    return text

@router.message(Command("start", "menu", "admin"))
async def cmd_start(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        await message.answer("⛔ <b>Access Denied:</b> You are not authorized to use this Promotion Control Bot.")
        return
    await state.clear()
    dashboard = await build_dashboard_text()
    await message.answer(dashboard, parse_mode="HTML", reply_markup=get_main_menu_keyboard())

@router.callback_query(F.data == "refresh_dashboard")
async def cb_refresh_dashboard(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        await query.answer("Access Denied", show_alert=True)
        return
    await state.clear()
    dashboard = await build_dashboard_text()
    try:
        await query.message.edit_text(dashboard, parse_mode="HTML", reply_markup=get_main_menu_keyboard())
    except Exception:
        pass
    await query.answer("Dashboard updated!")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        await query.answer("Access Denied", show_alert=True)
        return
    await state.clear()
    dashboard = await build_dashboard_text()
    try:
        await query.message.edit_text(dashboard, parse_mode="HTML", reply_markup=get_main_menu_keyboard())
    except Exception:
        pass
    await query.answer()
