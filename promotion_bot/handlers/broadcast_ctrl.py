import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import AsyncSessionLocal
from database.crud import get_setting, set_setting, get_active_groups
from core.broadcaster import broadcaster
import config

router = Router(name="broadcast_ctrl")

class IntervalStates(StatesGroup):
    waiting_for_custom_hours = State()

def get_broadcast_ctrl_keyboard(is_enabled: bool, is_running: bool, is_paused: bool) -> InlineKeyboardMarkup:
    kb = []
    
    # Run / Stop buttons
    if is_running:
        if is_paused:
            kb.append([InlineKeyboardButton(text="▶️ Resume Current Broadcast", callback_data="bc_resume")])
        else:
            kb.append([InlineKeyboardButton(text="⏸️ Pause Current Broadcast", callback_data="bc_pause")])
        kb.append([InlineKeyboardButton(text="🛑 Force Stop Current Round", callback_data="bc_stop_round")])
    else:
        kb.append([InlineKeyboardButton(text="🚀 Force Run 1 Round Now", callback_data="bc_run_now")])

    # Automation Switch
    toggle_text = "🔴 Disable Auto-Repeating" if is_enabled else "🟢 Enable Auto-Repeating"
    kb.append([InlineKeyboardButton(text=toggle_text, callback_data="bc_toggle_auto")])

    # Interval Chooser
    kb.append([
        InlineKeyboardButton(text="⏱️ 1 Hour", callback_data="bc_set_interval_1"),
        InlineKeyboardButton(text="⏱️ 2 Hours", callback_data="bc_set_interval_2"),
        InlineKeyboardButton(text="⏱️ 4 Hours", callback_data="bc_set_interval_4")
    ])
    kb.append([InlineKeyboardButton(text="⚙️ Custom Interval (Hours)", callback_data="bc_custom_interval")])
    kb.append([InlineKeyboardButton(text="📡 Live Progress Monitor", callback_data="bc_live_monitor")])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "menu_broadcast")
async def cb_broadcast_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()

    async with AsyncSessionLocal() as session:
        is_enabled = (await get_setting(session, "broadcast_enabled", "true")).lower() == "true"
        interval = await get_setting(session, "interval_hours", str(config.DEFAULT_INTERVAL_HOURS))
        groups = await get_active_groups(session)

    progress = broadcaster.get_progress_status()
    is_running = progress["is_running"]
    is_paused = progress.get("is_paused", False)

    state_badge = "🚀 RUNNING NOW" if is_running else ("🟢 AUTOMATICALLY SCHEDULED" if is_enabled else "🔴 PAUSED / OFF")

    text = (
        "🚀 <b>BROADCAST CONTROLS & SCHEDULER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📡 <b>Broadcaster State:</b> <code>{state_badge}</code>\n"
        f"⏱️ <b>Repeat Interval:</b> <code>Every {interval} Hours</code>\n"
        f"🎯 <b>Ready Target Groups:</b> <code>{len(groups)}</code>\n\n"
        "🛡️ <b>Anti-Ban Mathematics:</b>\n"
        "• Jitter delay: 18s - 35s per group\n"
        "• Batch cooldown: 4 min pause every 25 groups\n"
        "• Full cycle time for 350 groups ≈ 2.2 hours\n\n"
        "<i>Use the control buttons below:</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_broadcast_ctrl_keyboard(is_enabled, is_running, is_paused))
    await query.answer()

@router.callback_query(F.data == "bc_run_now")
async def cb_run_now(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    if broadcaster.is_broadcasting:
        await query.answer("A broadcast cycle is already actively running!", show_alert=True)
        return

    await query.answer("Starting on-demand broadcast round...", show_alert=True)
    asyncio.create_task(broadcaster.execute_broadcast_round(trigger_type="MANUAL_ADMIN"))
    await cb_broadcast_menu(query, None)

@router.callback_query(F.data == "bc_pause")
async def cb_pause(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    broadcaster.pause_broadcast()
    await query.answer("Broadcast paused.", show_alert=True)
    await cb_broadcast_menu(query, None)

@router.callback_query(F.data == "bc_resume")
async def cb_resume(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    broadcaster.resume_broadcast()
    await query.answer("Broadcast resumed!", show_alert=True)
    await cb_broadcast_menu(query, None)

@router.callback_query(F.data == "bc_stop_round")
async def cb_stop_round(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    broadcaster.stop_broadcast()
    await query.answer("Current round stopped.", show_alert=True)
    await cb_broadcast_menu(query, None)

@router.callback_query(F.data == "bc_toggle_auto")
async def cb_toggle_auto(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        cur = (await get_setting(session, "broadcast_enabled", "true")).lower() == "true"
        new_val = "false" if cur else "true"
        await set_setting(session, "broadcast_enabled", new_val)

    await query.answer(f"Auto-repeating is now {'ENABLED' if new_val == 'true' else 'DISABLED'}")
    await cb_broadcast_menu(query, None)

@router.callback_query(F.data.startswith("bc_set_interval_"))
async def cb_set_interval_quick(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    hours = query.data.replace("bc_set_interval_", "")
    async with AsyncSessionLocal() as session:
        await set_setting(session, "interval_hours", str(hours))

    await query.answer(f"Repeat interval set to {hours} hours!", show_alert=True)
    await cb_broadcast_menu(query, None)

@router.callback_query(F.data == "bc_custom_interval")
async def cb_custom_interval_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.set_state(IntervalStates.waiting_for_custom_hours)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_broadcast")]
    ])
    await query.message.edit_text(
        "⚙️ <b>Set Custom Broadcast Interval</b>\n\n"
        "Enter the repeat interval in hours (e.g. <code>1.5</code>, <code>2.5</code>, <code>3</code>):\n\n"
        "<i>Type the number below:</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await query.answer()

@router.message(IntervalStates.waiting_for_custom_hours)
async def handle_custom_hours(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    try:
        val = float(message.text.strip())
        if val < 0.5:
            await message.answer("⚠️ Minimum interval is 0.5 hours (30 minutes) to prevent Telegram spam bans.")
            return
        if val > 72:
            await message.answer("⚠️ Maximum interval is 72 hours.")
            return
    except ValueError:
        await message.answer("⚠️ Please enter a valid number (e.g. 1.5, 2, 3).")
        return

    async with AsyncSessionLocal() as session:
        await set_setting(session, "interval_hours", str(val))

    await state.clear()
    await message.answer(f"✅ <b>Repeat interval updated to every {val} hours!</b>", parse_mode="HTML")
    
    # Return to broadcast menu
    async with AsyncSessionLocal() as session:
        is_enabled = (await get_setting(session, "broadcast_enabled", "true")).lower() == "true"
        interval = await get_setting(session, "interval_hours", str(val))
        groups = await get_active_groups(session)
    progress = broadcaster.get_progress_status()
    text = (
        "🚀 <b>BROADCAST CONTROLS & SCHEDULER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏱️ <b>Repeat Interval:</b> <code>Every {interval} Hours</code>\n"
        f"🎯 <b>Ready Target Groups:</b> <code>{len(groups)}</code>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_broadcast_ctrl_keyboard(is_enabled, progress["is_running"], progress.get("is_paused", False)))

@router.callback_query(F.data == "bc_live_monitor")
async def cb_live_monitor(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    progress = broadcaster.get_progress_status()
    if not progress["is_running"]:
        await query.answer("No broadcast is currently running.", show_alert=True)
        return

    elapsed_m = progress["elapsed_seconds"] // 60
    elapsed_s = progress["elapsed_seconds"] % 60
    
    bar_len = 15
    filled = int((progress["current_index"] / max(progress["total_targets"], 1)) * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    text = (
        "📡 <b>LIVE BROADCAST MONITOR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Progress:</b> <code>[{bar}] {progress['progress_percent']}%</code>\n\n"
        f"• <b>Current Group:</b> <code>{progress['current_index']} / {progress['total_targets']}</code>\n"
        f"• ✅ <b>Successfully Delivered:</b> <code>{progress['success_count']}</code>\n"
        f"• ❌ <b>Failed / Banned:</b> <code>{progress['failed_count']}</code>\n"
        f"• ⏳ <b>Slowmode Skipped:</b> <code>{progress['skipped_count']}</code>\n"
        f"• ⏱️ <b>Elapsed Time:</b> <code>{elapsed_m}m {elapsed_s}s</code>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh Progress", callback_data="bc_live_monitor")],
        [InlineKeyboardButton(text="⬅️ Back to Broadcast Menu", callback_data="menu_broadcast")]
    ])
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()
