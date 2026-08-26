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
            InlineKeyboardButton(text="📢 Multi-Ad Campaigns Hub", callback_data="menu_campaigns")
        ],
        [
            InlineKeyboardButton(text="👥 Target Groups & Cleaner", callback_data="menu_groups"),
            InlineKeyboardButton(text="📱 Phone Numbers & OTP", callback_data="menu_auth")
        ],
        [
            InlineKeyboardButton(text="📊 Reports & Failure Logs", callback_data="menu_reports"),
            InlineKeyboardButton(text="⚙️ Scheduler & Anti-Ban", callback_data="menu_settings")
        ],
        [
            InlineKeyboardButton(text="🔄 Refresh Dashboard", callback_data="refresh_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def build_dashboard_text() -> str:
    async with AsyncSessionLocal() as session:
        stats = await get_group_stats(session)
        is_enabled = await get_setting(session, "broadcast_enabled", "true")
        interval = await get_setting(session, "interval_hours", str(config.DEFAULT_INTERVAL_HOURS))
        all_accounts = await get_all_sender_accounts(session)

    # Broadcaster Status summary
    running_workers = [w for w in broadcaster.workers.values() if w.get("is_running")]
    if running_workers:
        workers_text = "\n".join([
            f"   • 📱 <code>{w.get('account_phone')}</code>: 🚀 <b>RUNNING</b> ({w.get('current_index')}/{w.get('total_targets')} — {round((w.get('current_index', 0)/max(w.get('total_targets', 1), 1))*100, 1)}%)"
            for w in running_workers
        ])
        status_badge = f"🚀 <b>{len(running_workers)} WORKER(S) BROADCASTING</b>\n{workers_text}"
    else:
        sched_state = "🟢 <b>AUTOMATICALLY SCHEDULED</b>" if is_enabled.lower() == "true" else "🔴 <b>STOPPED / PAUSED</b>"
        status_badge = f"{sched_state} (Every {interval} Hours)"

    # Account list summary
    if all_accounts:
        acc_lines = []
        for a in all_accounts:
            prem = "👑" if a.is_premium else "📱"
            acc_lines.append(f"• {prem} <code>{a.phone}</code> (@{a.username or a.first_name or 'NoUser'})")
        accounts_text = "\n".join(acc_lines)
    else:
        accounts_text = "<i>No phone accounts added yet. (Tap 'Phone Numbers & OTP' below)</i>"

    text = (
        "🤖 <b>SAMSTORE TELEGRAM PROMOTION BOT — CONTROL CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📱 <b>Connected Sender Accounts:</b>\n"
        f"{accounts_text}\n\n"
        "📡 <b>Live Broadcast Status:</b>\n"
        f"{status_badge}\n\n"
        "👥 <b>Target Groups Database:</b>\n"
        f"• 🎯 Total Saved Groups: <code>{stats.get('TOTAL', 0)}</code>\n"
        f"• 🟢 Active & Ready: <code>{stats.get('ACTIVE', 0)}</code>\n"
        f"• ⚠️ Banned / Restricted: <code>{stats.get('BANNED', 0) + stats.get('RESTRICTED', 0)}</code>\n"
        f"• 🚫 Invalid / Dead Links: <code>{stats.get('INVALID_LINK', 0)}</code>\n\n"
        "🛡️ <b>Anti-Ban Protection:</b> <code>18s–35s Random Jitter + Anti-Hash Spintax</code>\n\n"
        "<i>Select a section below to manage your campaigns:</i>"
    )
    return text

@router.message(Command("start", "menu", "admin"))
async def cmd_start(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        await message.answer("⛔ <b>Access Denied:</b> You are not authorized to use this bot.")
        return
    if state is not None:
        await state.clear()
    dashboard = await build_dashboard_text()
    await message.answer(dashboard, parse_mode="HTML", reply_markup=get_main_menu_keyboard())

@router.callback_query(F.data == "refresh_dashboard")
async def cb_refresh_dashboard(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        await query.answer("Access Denied", show_alert=True)
        return
    if state is not None:
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
    if state is not None:
        await state.clear()
    dashboard = await build_dashboard_text()
    try:
        await query.message.edit_text(dashboard, parse_mode="HTML", reply_markup=get_main_menu_keyboard())
    except Exception:
        pass
    await query.answer()
