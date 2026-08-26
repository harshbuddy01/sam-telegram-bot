from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from database.crud import get_setting, set_setting
import config

router = Router(name="settings_menu")

def get_settings_keyboard(spintax_enabled: bool) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(
                text=f"🌀 Spintax & Anti-Hash: {'🟢 ON' if spintax_enabled else '🔴 OFF'}",
                callback_data="toggle_spintax"
            )
        ],
        [
            InlineKeyboardButton(text="⚡ Conservative (Extra Safe)", callback_data="preset_safe"),
            InlineKeyboardButton(text="🚀 Balanced (Recommended)", callback_data="preset_balanced")
        ],
        [
            InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "menu_settings")
async def cb_settings_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()

    async with AsyncSessionLocal() as session:
        min_d = await get_setting(session, "min_delay_sec", str(config.MIN_DELAY_PER_GROUP))
        max_d = await get_setting(session, "max_delay_sec", str(config.MAX_DELAY_PER_GROUP))
        batch_sz = await get_setting(session, "batch_size", str(config.BATCH_SIZE))
        cooldown = await get_setting(session, "batch_cooldown_sec", str(config.BATCH_COOLDOWN))
        spintax = (await get_setting(session, "spintax_enabled", "true")).lower() == "true"

    text = (
        "🛡️ <b>ANTI-BAN SAFETY & MATHEMATICAL ENGINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Current Safety Calibrations:</b>\n"
        f"• <b>Random Jitter Delay:</b> <code>{min_d}s – {max_d}s per group</code>\n"
        f"• <b>Batch Pause:</b> <code>{cooldown}s cooldown after every {batch_sz} groups</code>\n"
        f"• <b>Anti-Hash Spintax Engine:</b> <code>{'ENABLED' if spintax else 'DISABLED'}</code>\n\n"
        "📊 <b>Mathematical Analysis for 350 Groups:</b>\n"
        f"• Average time per group: ~{(int(min_d) + int(max_d)) // 2} seconds\n"
        f"• Total active broadcast time: ~2.0 to 2.5 hours\n"
        "• Telegram Message Rate: ~2.3 msgs/min (<i>Far below Telegram's 20 msgs/min threshold!</i>)\n\n"
        "<i>Presets:</i>\n"
        "• <b>Balanced (Recommended):</b> 18–35s delays, 4m cooldown per 25 groups\n"
        "• <b>Conservative:</b> 25–45s delays, 5m cooldown per 20 groups"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_settings_keyboard(spintax))
    await query.answer()

@router.callback_query(F.data == "toggle_spintax")
async def cb_toggle_spintax(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        curr = (await get_setting(session, "spintax_enabled", "true")).lower() == "true"
        new_v = "false" if curr else "true"
        await set_setting(session, "spintax_enabled", new_v)

    await query.answer(f"Spintax is now {'ENABLED' if new_v == 'true' else 'DISABLED'}")
    await cb_settings_menu(query, None)

@router.callback_query(F.data == "preset_balanced")
async def cb_preset_balanced(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        await set_setting(session, "min_delay_sec", "18")
        await set_setting(session, "max_delay_sec", "35")
        await set_setting(session, "batch_size", "25")
        await set_setting(session, "batch_cooldown_sec", "240")

    await query.answer("Applied Balanced Anti-Ban Preset!", show_alert=True)
    await cb_settings_menu(query, None)

@router.callback_query(F.data == "preset_safe")
async def cb_preset_safe(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        await set_setting(session, "min_delay_sec", "25")
        await set_setting(session, "max_delay_sec", "45")
        await set_setting(session, "batch_size", "20")
        await set_setting(session, "batch_cooldown_sec", "300")

    await query.answer("Applied Conservative Safe Anti-Ban Preset!", show_alert=True)
    await cb_settings_menu(query, None)
