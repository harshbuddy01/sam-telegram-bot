from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from database.database import AsyncSessionLocal
from database.crud import (
    get_recent_cycles,
    get_cycle_by_id,
    get_cycle_sent_logs,
    get_cycle_failed_logs,
    get_groups_by_status,
    smart_clean_and_purge_groups
)
import config

router = Router(name="stats_report")

def get_reports_menu_keyboard(cycles: list) -> InlineKeyboardMarkup:
    kb = []
    for c in cycles:
        dt_str = c.started_at.strftime("%b %d, %H:%M") if c.started_at else "Recent"
        phone_tag = f"[{c.account_phone[-4:] if c.account_phone else 'All'}]"
        btn_text = f"📱 {phone_tag} Cycle #{c.id} ({dt_str}) — ✅{c.success_count} ❌{c.failed_count}"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"cycle_detail_{c.id}")])
    
    kb.append([
        InlineKeyboardButton(text="🧹 Smart Clean All Dead Links", callback_data="report_smart_clean"),
        InlineKeyboardButton(text="📄 Export Failed (.TXT)", callback_data="export_failed_txt")
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "menu_reports")
async def cb_reports_menu(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    if state is not None:
        await state.clear()

    async with AsyncSessionLocal() as session:
        cycles = await get_recent_cycles(session, limit=6)

    if not cycles:
        text = (
            "📊 <b>BROADCAST REPORTS & FAILURE TRACKING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>No broadcast cycles have run yet. Once a campaign starts, detailed logs will appear here!</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")]
        ])
        try:
            await query.message.edit_text(text, parse_mode="HTML, reply_markup=kb")
        except TelegramBadRequest:
            pass
        await query.answer()
        return

    text = (
        "📊 <b>RECENT BROADCAST CYCLES & LOGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<i>Select any cycle below to inspect delivered vs failed groups and exact reasons:</i>"
    )
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_reports_menu_keyboard(cycles))
    except TelegramBadRequest:
        pass
    await query.answer()

@router.callback_query(F.data.startswith("cycle_detail_"))
async def cb_cycle_detail(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    cycle_id = int(query.data.replace("cycle_detail_", ""))

    async with AsyncSessionLocal() as session:
        cycle = await get_cycle_by_id(session, cycle_id)
        failed_logs = await get_cycle_failed_logs(session, cycle_id)
        sent_logs = await get_cycle_sent_logs(session, cycle_id)

    phone_badge = f"📱 <b>Sender Account:</b> <code>{cycle.account_phone or 'Primary'}</code>\n" if cycle else ""
    duration_str = f"⏱️ <b>Duration:</b> {cycle.duration_seconds // 60}m {cycle.duration_seconds % 60}s\n" if cycle and cycle.duration_seconds else ""

    if not failed_logs and not sent_logs:
        text = (
            f"📊 <b>Cycle #{cycle_id} Report</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{phone_badge}{duration_str}\n"
            "<i>No logs recorded for this cycle.</i>"
        )
    else:
        log_lines = []
        for log in failed_logs[:12]:
            reason = log.error_reason or "Unknown"
            log_lines.append(f"• <b>{log.group_identifier}</b>: <code>{reason}</code>")
            
        extra = f"\n<i>...and {len(failed_logs) - 12} more failed.</i>" if len(failed_logs) > 12 else ""
        failed_section = "\n".join(log_lines) if log_lines else "<i>None! 100% delivered.</i>"

        text = (
            f"📊 <b>CYCLE #{cycle_id} BREAKDOWN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{phone_badge}{duration_str}"
            f"• ✅ <b>Successfully Delivered:</b> <code>{len(sent_logs)} groups</code>\n"
            f"• ❌ <b>Failed / Restricted:</b> <code>{len(failed_logs)} groups</code>\n\n"
            "⚠️ <b>Failed Groups Breakdown:</b>\n"
            f"{failed_section}{extra}\n\n"
            "💡 <i>You can purge all dead/invalid links with 1 click below:</i>"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Smart Clean Dead Links", callback_data="report_smart_clean")],
        [InlineKeyboardButton(text="⬅️ Back to Reports", callback_data="menu_reports")]
    ])
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        pass
    await query.answer()

@router.callback_query(F.data == "report_smart_clean")
async def cb_report_smart_clean(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        res = await smart_clean_and_purge_groups(session)
    
    await query.answer(f"🧹 Cleaned {res['deleted']} invalid/dead links! {res['active']} active groups remaining.", show_alert=True)
    await cb_reports_menu(query, None)

@router.callback_query(F.data == "export_failed_txt")
async def cb_export_failed(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        banned = await get_groups_by_status(session, "BANNED")
        restricted = await get_groups_by_status(session, "RESTRICTED")
        invalid = await get_groups_by_status(session, "INVALID_LINK")

    all_failed = banned + restricted + invalid
    if not all_failed:
        await query.answer("No failed groups currently in database!", show_alert=True)
        return

    lines = ["GROUP_IDENTIFIER | STATUS | REASON"]
    for g in all_failed:
        lines.append(f"{g.identifier} | {g.status} | {g.last_error or 'None'}")

    file_content = "\n".join(lines).encode("utf-8")
    doc = BufferedInputFile(file_content, filename="failed_groups_report.txt")
    await query.message.answer_document(doc, caption=f"📄 <b>Failed Groups Export ({len(all_failed)} total)</b>", parse_mode="HTML")
    await query.answer()
