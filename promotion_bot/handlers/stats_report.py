from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from database.crud import get_recent_cycles, get_cycle_failed_logs, get_groups_by_status
import config

router = Router(name="stats_report")

def get_reports_menu_keyboard(cycles: list) -> InlineKeyboardMarkup:
    kb = []
    for c in cycles:
        dt_str = c.started_at.strftime("%b %d, %H:%M") if c.started_at else "Recent"
        btn_text = f"Cycle #{c.id} ({dt_str}) — ✅{c.success_count} ❌{c.failed_count}"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"cycle_detail_{c.id}")])
    
    kb.append([InlineKeyboardButton(text="📄 Export All Failed Groups (TXT)", callback_data="export_failed_txt")])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "menu_reports")
async def cb_reports_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()

    async with AsyncSessionLocal() as session:
        cycles = await get_recent_cycles(session, limit=5)

    if not cycles:
        text = (
            "📊 <b>BROADCAST REPORTS & FAILURE TRACKING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>No broadcast cycles have run yet. Once a round starts, detailed logs will appear here!</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")]
        ])
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await query.answer()
        return

    text = (
        "📊 <b>RECENT BROADCAST CYCLES & LOGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select any cycle below to inspect failed groups and exact reasons:\n"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_reports_menu_keyboard(cycles))
    await query.answer()

@router.callback_query(F.data.startswith("cycle_detail_"))
async def cb_cycle_detail(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    cycle_id = int(query.data.replace("cycle_detail_", ""))

    async with AsyncSessionLocal() as session:
        failed_logs = await get_cycle_failed_logs(session, cycle_id)

    if not failed_logs:
        text = (
            f"📊 <b>Cycle #{cycle_id} Failure Report</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎉 <b>100% Clean!</b> No groups failed or encountered errors in this round."
        )
    else:
        log_lines = []
        for log in failed_logs[:15]:
            reason = log.error_reason or "Unknown"
            log_lines.append(f"• <b>{log.group_identifier}</b>: <code>{reason}</code>")
            
        extra = f"\n<i>...and {len(failed_logs) - 15} more.</i>" if len(failed_logs) > 15 else ""
        text = (
            f"📊 <b>Cycle #{cycle_id} — Failed Groups ({len(failed_logs)})</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{chr(10).join(log_lines)}{extra}\n\n"
            "💡 <i>These groups are flagged in the database so your account isn't repeatedly blocked.</i>"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Cycles", callback_data="menu_reports")]
    ])
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()

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
        lines.append(f"{g.identifier} | {g.status} | {g.last_error or 'N/A'}")

    content = "\n".join(lines).encode("utf-8")
    doc = BufferedInputFile(content, filename="failed_groups_report.txt")
    await query.message.answer_document(doc, caption=f"📄 <b>Failed Groups Export ({len(all_failed)} groups)</b>", parse_mode="HTML")
    await query.answer()
