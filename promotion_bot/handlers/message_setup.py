import os
import html
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, PhotoSize, Video
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    get_or_create_account_promo,
    update_account_promo,
)
from utils.spintax import prepare_broadcast_message
from utils.premium_emojis import parse_shortcodes_to_tg_emoji
import config

router = Router()


class MessageStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()


@router.callback_query(F.data == "sec_message")
async def cb_message_setup_menu(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass
    if state:
        await state.clear()

    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        promos_map = {}
        for acc in accounts:
            p = await get_or_create_account_promo(session, acc.id, acc.phone)
            promos_map[acc.id] = p

    text = (
        "✏️ <b>MESSAGE SETUP — SELECT SENDER NUMBER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Configure custom promotional messages & media per phone number:\n\n"
    )

    kb = []
    if not accounts:
        text += "<i>No phone numbers connected. Please add a number first in 📱 Add Numbers.</i>"
    else:
        for acc in accounts:
            promo = promos_map[acc.id]
            media_badge = f" [📷 {promo.media_type.upper()}]" if promo.media_type != "none" else ""
            user_lbl = f"@{acc.username}" if acc.username else (acc.first_name or "")
            text += (
                f"📱 <b>{acc.phone}</b> ({user_lbl}){media_badge}\n"
                f"   • Snippet: <i>{html.escape(promo.text[:50])}...</i>\n\n"
            )
            kb.append([
                InlineKeyboardButton(
                    text=f"✏️ Setup Message for {acc.phone}",
                    callback_data=f"msg_acc_{acc.id}"
                )
            ])

    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("msg_acc_"))
async def cb_message_account_editor(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass
    if state:
        await state.clear()

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        acc = next((a for a in accounts if a.id == account_id), None)
        if not acc:
            return
        promo = await get_or_create_account_promo(session, account_id, acc.phone)

    user_lbl = f"@{acc.username}" if acc.username else (acc.first_name or "")
    media_info = f"<code>{promo.media_type.upper()}</code>" if promo.media_type != "none" else "<i>None (Text Only)</i>"

    text = (
        f"✏️ <b>AD PROMO EDITOR — {acc.phone}</b> ({user_lbl})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🖼️ <b>Attached Media:</b> {media_info}\n\n"
        f"📝 <b>Current Message Template:</b>\n"
        f"<blockquote>{html.escape(promo.text)}</blockquote>\n\n"
        "💡 <i>HTML tags and Spintax variation syntax <code>{{option1|option2}}</code> are fully supported.</i>"
    )

    kb = [
        [
            InlineKeyboardButton(text="✏️ Edit Text", callback_data=f"msg_edit_text_{account_id}"),
            InlineKeyboardButton(text="📷 Set Photo/Video", callback_data=f"msg_edit_media_{account_id}")
        ],
        [
            InlineKeyboardButton(text="👁️ Live Preview", callback_data=f"msg_preview_{account_id}"),
            InlineKeyboardButton(text="🗑️ Remove Media", callback_data=f"msg_rm_media_{account_id}")
        ],
        [
            InlineKeyboardButton(text="💡 Spintax Help", callback_data="msg_spintax_help"),
            InlineKeyboardButton(text="⭐ Custom Emoji Help", callback_data="msg_emoji_help")
        ],
        [InlineKeyboardButton(text="⬅️ Back to Numbers List", callback_data="sec_message")]
    ]

    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("msg_edit_text_"))
async def cb_edit_text_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[3])
    await state.set_state(MessageStates.waiting_for_text)
    await state.update_data(target_account_id=account_id)

    text = (
        "✏️ <b>SEND NEW PROMOTIONAL TEXT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Send your message text now.\n\n"
        "<b>Supported Features:</b>\n"
        "• <b>HTML tags:</b> <code>&lt;b&gt;bold&lt;/b&gt;</code>, <code>&lt;i&gt;italic&lt;/i&gt;</code>, <code>&lt;a href='...'&gt;links&lt;/a&gt;</code>\n"
        "• <b>Spintax:</b> <code>{{Hello|Hey|Hi}} there!</code> (rotates per group)\n"
        "• <b>Zero-Width Anti-Hash:</b> automatically applied on broadcast"
    )
    kb = [[InlineKeyboardButton(text="❌ Cancel", callback_data=f"msg_acc_{account_id}")]]
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.message(MessageStates.waiting_for_text)
async def handle_new_text_input(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    account_id = data.get("target_account_id")
    await state.clear()

    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.answer("⚠️ Message cannot be empty. Please try again.")
        return

    async with AsyncSessionLocal() as session:
        await update_account_promo(session, account_id, new_text.strip())

    text = (
        "✅ <b>PROMO MESSAGE UPDATED SUCCESSFULLY!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>New Text Preview:</b>\n"
        f"<blockquote>{html.escape(new_text.strip())}</blockquote>"
    )
    kb = [
        [InlineKeyboardButton(text="👁️ Live Preview", callback_data=f"msg_preview_{account_id}")],
        [InlineKeyboardButton(text="✏️ Back to Editor", callback_data=f"msg_acc_{account_id}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("msg_edit_media_"))
async def cb_edit_media_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[3])
    await state.set_state(MessageStates.waiting_for_media)
    await state.update_data(target_account_id=account_id)

    text = (
        "📷 <b>UPLOAD MEDIA (PHOTO OR VIDEO)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the Photo or Video you want attached to your promotional broadcast.\n\n"
        "💡 <i>If you include a caption with your photo/video, it will also be saved as your ad text!</i>"
    )
    kb = [[InlineKeyboardButton(text="❌ Cancel", callback_data=f"msg_acc_{account_id}")]]
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.message(MessageStates.waiting_for_media)
async def handle_new_media_input(message: Message, state: FSMContext, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    account_id = data.get("target_account_id")
    await state.clear()

    os.makedirs(config.MEDIA_STORAGE_PATH, exist_ok=True)

    media_type = "none"
    media_file_id = None
    media_path = None
    caption_text = message.caption

    if message.photo:
        media_type = "photo"
        photo: PhotoSize = message.photo[-1]
        media_file_id = photo.file_id
        media_path = os.path.join(config.MEDIA_STORAGE_PATH, f"promo_acc_{account_id}.jpg")
        await bot.download(photo, destination=media_path)
    elif message.video:
        media_type = "video"
        vid: Video = message.video
        media_file_id = vid.file_id
        media_path = os.path.join(config.MEDIA_STORAGE_PATH, f"promo_acc_{account_id}.mp4")
        await bot.download(vid, destination=media_path)
    else:
        await message.answer("⚠️ Please send a valid Photo or Video.")
        return

    async with AsyncSessionLocal() as session:
        promo = await get_or_create_account_promo(session, account_id)
        final_text = caption_text.strip() if caption_text else promo.text
        await update_account_promo(
            session, account_id, final_text,
            media_type=media_type, media_file_id=media_file_id, media_path=media_path
        )

    text = (
        f"✅ <b>{media_type.upper()} ATTACHED SUCCESSFULLY!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Saved to: <code>{media_path}</code>\n\n"
        "<i>Your media will be delivered alongside the promotional message in groups!</i>"
    )
    kb = [
        [InlineKeyboardButton(text="👁️ Live Preview", callback_data=f"msg_preview_{account_id}")],
        [InlineKeyboardButton(text="✏️ Back to Editor", callback_data=f"msg_acc_{account_id}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("msg_rm_media_"))
async def cb_remove_media(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[3])

    async with AsyncSessionLocal() as session:
        promo = await get_or_create_account_promo(session, account_id)
        if promo.media_path and os.path.exists(promo.media_path):
            try:
                os.remove(promo.media_path)
            except Exception:
                pass
        await update_account_promo(
            session, account_id, promo.text,
            media_type="none", media_file_id=None, media_path=None
        )

    try:
        await query.answer("🗑️ Media removed! Ad is now Text Only.", show_alert=True)
    except Exception:
        pass
    await cb_message_account_editor(query)


@router.callback_query(F.data.startswith("msg_preview_"))
async def cb_preview_promo(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        promo = await get_or_create_account_promo(session, account_id)

    processed_text = prepare_broadcast_message(promo.text, apply_spintax=True, apply_jitter=False)
    processed_text = parse_shortcodes_to_tg_emoji(processed_text)

    preview_header = "👁️ <b>LIVE BROADCAST PREVIEW</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    try:
        if promo.media_type == "photo" and promo.media_file_id:
            await query.message.answer_photo(
                photo=promo.media_file_id,
                caption=f"{preview_header}{processed_text}",
                parse_mode="HTML"
            )
        elif promo.media_type == "video" and promo.media_file_id:
            await query.message.answer_video(
                video=promo.media_file_id,
                caption=f"{preview_header}{processed_text}",
                parse_mode="HTML"
            )
        else:
            await query.message.answer(
                f"{preview_header}{processed_text}",
                parse_mode="HTML",
                disable_web_page_preview=False
            )
    except Exception as e:
        await query.message.answer(f"⚠️ Preview render error (check HTML syntax): <code>{e}</code>", parse_mode="HTML")


@router.callback_query(F.data == "msg_spintax_help")
async def cb_spintax_help(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    text = (
        "💡 <b>HOW SPINTAX WORKS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Spintax allows you to create thousands of unique variations of your message so Telegram cannot detect automated broadcasting.\n\n"
        "<b>Syntax:</b>\n"
        "<code>{{Option 1|Option 2|Option 3}}</code>\n\n"
        "<b>Example:</b>\n"
        "<code>{{🔥 Big Sale|⚡ Exclusive Offer|🎁 Special Discount}}! Contact {{us now|support}} for details!</code>\n\n"
        "<b>Generates variations like:</b>\n"
        "1. <i>🔥 Big Sale! Contact us now for details!</i>\n"
        "2. <i>⚡ Exclusive Offer! Contact support for details!</i>\n"
        "3. <i>🎁 Special Discount! Contact us now for details!</i>"
    )
    kb = [[InlineKeyboardButton(text="⬅️ Back", callback_data="sec_message")]]
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data == "msg_emoji_help")
async def cb_emoji_help(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    text = (
        "⭐ <b>CUSTOM PREMIUM EMOJI SHORTCODES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "You can insert animated custom emojis using simple shortcodes:\n\n"
        "<b>Available Shortcodes:</b>\n"
        "• <code>:crown:</code> 👑 Crown\n"
        "• <code>:fire:</code> 🔥 Fire\n"
        "• <code>:diamond:</code> 💎 Diamond\n"
        "• <code>:star:</code> ⭐ Star\n"
        "• <code>:verified:</code> 🛡️ Verified Badge\n"
        "• <code>:check:</code> ✅ Checkmark\n"
        "• <code>:netflix:</code> 🎬 Netflix\n"
        "• <code>:prime:</code> 📦 Prime Video\n"
        "• <code>:chatgpt:</code> 🤖 ChatGPT\n"
        "• <code>:claude:</code> 🧠 Claude AI\n"
        "• <code>:spotify:</code> 🎵 Spotify"
    )
    kb = [[InlineKeyboardButton(text="⬅️ Back", callback_data="sec_message")]]
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
