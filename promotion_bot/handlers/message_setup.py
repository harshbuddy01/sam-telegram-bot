import os
import html
import re
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
from core.client import tg_manager
import config

router = Router()


async def _safe_send_message(query: CallbackQuery, text: str, kb: list, is_edit: bool = True):
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    try:
        if is_edit:
            await query.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        else:
            await query.message.answer(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        plain_text = re.sub(r'<[^>]+>', '', text)
        try:
            if is_edit:
                await query.message.edit_text(plain_text, reply_markup=markup)
            else:
                await query.message.answer(plain_text, reply_markup=markup)
        except Exception:
            pass


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
            user_lbl = html.escape(f"@{acc.username}" if acc.username else (acc.first_name or ""))
            clean_snippet = html.escape(re.sub(r'<[^>]+>', '', promo.text or "")[:50].strip())
            text += (
                f"📱 <b>{acc.phone}</b> ({user_lbl}){media_badge}\n"
                f"   • Snippet: <i>{clean_snippet}...</i>\n\n"
            )
            kb.append([
                InlineKeyboardButton(
                    text=f"✏️ Setup Message for {acc.phone}",
                    callback_data=f"msg_acc_{acc.id}"
                )
            ])

    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    await _safe_send_message(query, text, kb, is_edit=True)


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

    user_lbl = html.escape(f"@{acc.username}" if acc.username else (acc.first_name or ""))
    media_info = f"<code>{promo.media_type.upper()}</code>" if promo.media_type != "none" else "<i>None (Text Only)</i>"

    source_info = f"<code>Saved Messages (ID: {promo.saved_msg_id})</code>" if getattr(promo, "saved_msg_id", None) else "<i>Custom Text Editor</i>"

    text = (
        f"✏️ <b>AD PROMO EDITOR — {acc.phone}</b> ({user_lbl})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Ad Source:</b> {source_info}\n"
        f"🖼️ <b>Attached Media:</b> {media_info}\n\n"
        f"📝 <b>Current Message Template:</b>\n"
        f"<blockquote>{html.escape(promo.text)}</blockquote>\n\n"
        "💡 <i>Tip: Send your ad with custom animated emojis to Saved Messages in Telegram, then tap <b>📥 Pull from Saved Messages</b> below!</i>"
    )

    kb = [
        [
            InlineKeyboardButton(text="📥 Pull from Saved Messages", callback_data=f"msg_sync_saved_{account_id}")
        ],
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

    await _safe_send_message(query, text, kb, is_edit=True)


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


from utils.emoji_extractor import extract_html_with_premium_emojis


@router.message(MessageStates.waiting_for_text)
async def handle_new_text_input(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    account_id = data.get("target_account_id")
    await state.clear()

    # Extract HTML preserving native Telegram Premium custom emojis and text formatting
    new_text = extract_html_with_premium_emojis(message)
    if not new_text.strip():
        await message.answer("⚠️ Message cannot be empty. Please try again.")
        return

    async with AsyncSessionLocal() as session:
        await update_account_promo(session, account_id, new_text.strip())

    text = (
        "✅ <b>PROMO MESSAGE UPDATED SUCCESSFULLY!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>New Text Preview:</b>\n"
        f"{new_text.strip()}\n\n"
        "💡 <i>Native Telegram Premium animated emojis & formatting have been preserved!</i>"
    )
    kb = [
        [InlineKeyboardButton(text="👁️ Live Preview", callback_data=f"msg_preview_{account_id}")],
        [InlineKeyboardButton(text="✏️ Back to Editor", callback_data=f"msg_acc_{account_id}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    try:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        plain_text = re.sub(r'<[^>]+>', '', text)
        await message.answer(plain_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


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
        "💡 <i>If you include a caption with your photo/video (including Premium emojis), it will also be saved as your ad text!</i>"
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
    caption_text = extract_html_with_premium_emojis(message)

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
        plain_processed = re.sub(r'<[^>]+>', '', processed_text)
        await query.message.answer(
            f"👁️ <b>LIVE BROADCAST PREVIEW (Plain Text Fallback)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{html.escape(plain_processed)}\n\n"
            f"⚠️ <i>Note: Your HTML formatting contains syntax errors:</i>\n"
            f"<code>{html.escape(str(e))}</code>\n\n"
            f"👉 <i>Please edit the message text and check for unclosed HTML tags.</i>",
            parse_mode="HTML"
        )


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


@router.callback_query(F.data.startswith("msg_sync_saved_"))
async def cb_sync_saved_messages(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[3])

    client = await tg_manager.get_client_for_account(account_id)
    if not client or not await client.is_user_authorized():
        await query.message.answer(
            "❌ <b>Account Not Connected!</b>\n"
            "This sender account is not authorized. Please check 📱 Add Numbers.",
            parse_mode="HTML"
        )
        return

    try:
        await query.message.answer(
            "⏳ <b>Reading Saved Messages...</b>\n"
            "Fetching the latest message from this account's Saved Messages (<code>'me'</code>).",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        # Fetch latest message with content from Saved Messages ('me')
        messages = await client.get_messages("me", limit=5)
        saved_msg = next((m for m in messages if m.message or m.media), None)

        if not saved_msg:
            await query.message.answer(
                "⚠️ <b>No Messages Found in Saved Messages!</b>\n\n"
                "Please open Telegram on this phone, go to <b>Saved Messages</b>, and send/paste your promotional ad with text, custom emojis, or photo/video.\n\n"
                "Then tap <b>📥 Pull from Saved Messages</b> again!",
                parse_mode="HTML"
            )
            return

        saved_text = saved_msg.message or ""
        media_type = "none"
        media_path = None

        # Download media locally if photo or video
        if saved_msg.media:
            os.makedirs(config.MEDIA_STORAGE_PATH, exist_ok=True)
            if getattr(saved_msg, "photo", None):
                media_type = "photo"
                dest_file = os.path.join(config.MEDIA_STORAGE_PATH, f"promo_{account_id}_saved.jpg")
                media_path = await client.download_media(saved_msg, file=dest_file)
            elif getattr(saved_msg, "video", None):
                media_type = "video"
                dest_file = os.path.join(config.MEDIA_STORAGE_PATH, f"promo_{account_id}_saved.mp4")
                media_path = await client.download_media(saved_msg, file=dest_file)

        async with AsyncSessionLocal() as session:
            await update_account_promo(
                session,
                account_id,
                text=saved_text,
                media_type=media_type,
                media_path=media_path,
                saved_msg_id=saved_msg.id
            )

        preview_snippet = html.escape(saved_text[:250]) + ("..." if len(saved_text) > 250 else "")
        confirm_text = (
            f"✅ <b>Successfully Synced from Saved Messages!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Saved Message ID:</b> <code>{saved_msg.id}</code>\n"
            f"🖼️ <b>Media Type:</b> <code>{media_type.upper()}</code>\n"
            f"📝 <b>Text Preview:</b>\n"
            f"<blockquote>{preview_snippet}</blockquote>\n\n"
            f"✨ <i>All native custom emojis, stickers, fonts, and media will be preserved during broadcasts!</i>"
        )
        kb = [[InlineKeyboardButton(text="⬅️ Return to Message Editor", callback_data=f"msg_acc_{account_id}")]]
        await query.message.answer(confirm_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

    except Exception as e:
        await query.message.answer(
            f"❌ <b>Error syncing from Saved Messages:</b> <code>{html.escape(str(e))}</code>",
            parse_mode="HTML"
        )
