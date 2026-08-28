import os
import re
import asyncio
import random
import time
import datetime
import logging

from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    SlowModeWaitError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatSendMediaForbiddenError,
    PeerFloodError,
    AuthKeyUnregisteredError,
    SessionRevokedError,
    UserDeactivatedError,
    UserDeactivatedBanError,
    UserAlreadyParticipantError,
)

from core.client import tg_manager
from core.joiner import extract_group_identifier
from utils.spintax import prepare_broadcast_message
from utils.premium_emojis import parse_shortcodes_to_tg_emoji
from database.database import AsyncSessionLocal
from database.crud import (
    get_selected_groups,
    get_or_create_account_promo,
    get_all_sender_accounts,
    get_active_sender_account,
    update_group_status,
    update_sender_account_status,
    delete_group,
    create_cycle,
    finish_cycle,
    log_broadcast_result,
    get_setting,
)
import config

logger = logging.getLogger(__name__)


class SafeBroadcaster:
    def __init__(self):
        # account_id -> worker state dict
        self.workers: dict[int, dict] = {}
        self.bot_instance = None  # Reference to Aiogram Bot to send notifications

    def set_bot_instance(self, bot):
        self.bot_instance = bot

    @property
    def is_broadcasting(self) -> bool:
        return any(w.get("is_running", False) for w in self.workers.values())

    @property
    def is_paused(self) -> bool:
        return any(w.get("is_paused", False) for w in self.workers.values())

    def is_account_broadcasting(self, account_id: int) -> bool:
        w = self.workers.get(account_id)
        return w is not None and w.get("is_running", False)

    async def notify_admins(self, text: str):
        if not self.bot_instance:
            return
        for admin_id in config.ADMIN_IDS:
            try:
                await self.bot_instance.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")

    def get_progress_status(self, account_id: int = None) -> dict:
        """Returns live progress metrics for a specific account or the primary active worker."""
        if account_id and account_id in self.workers:
            w = self.workers[account_id]
        elif self.workers:
            running_w = next((w for w in self.workers.values() if w.get("is_running")), None)
            w = running_w or next(iter(self.workers.values()))
        else:
            return {"is_running": False}

        if not w.get("is_running"):
            return {"is_running": False, "account_phone": w.get("account_phone", "N/A")}

        elapsed = int(time.time() - w.get("start_time", time.time()))
        total = w.get("total_targets", 0)
        curr = w.get("current_index", 0)
        remaining = max(0, total - curr)

        return {
            "is_running": True,
            "is_paused": w.get("is_paused", False),
            "account_id": w.get("account_id"),
            "account_phone": w.get("account_phone"),
            "cycle_id": w.get("cycle_id"),
            "current_index": curr,
            "total_targets": total,
            "success_count": w.get("success_count", 0),
            "failed_count": w.get("failed_count", 0),
            "skipped_count": w.get("skipped_count", 0),
            "remaining_count": remaining,
            "elapsed_seconds": elapsed,
            "progress_percent": round((curr / max(total, 1)) * 100, 1),
        }

    def get_all_workers_status(self) -> list[dict]:
        """Returns status list for all accounts."""
        results = []
        for acc_id, w in self.workers.items():
            results.append({
                "account_id": acc_id,
                "account_phone": w.get("account_phone"),
                "is_running": w.get("is_running", False),
                "is_paused": w.get("is_paused", False),
                "current_index": w.get("current_index", 0),
                "total_targets": w.get("total_targets", 0),
                "success_count": w.get("success_count", 0),
                "failed_count": w.get("failed_count", 0),
                "progress_percent": round(
                    (w.get("current_index", 0) / max(w.get("total_targets", 1), 1)) * 100, 1
                ),
            })
        return results

    async def send_to_single_group(
        self, client: TelegramClient, group, promo, dialog_entities: dict | None = None
    ) -> dict:
        identifier = group.identifier

        # Prepare unique anti-hash Spintax variation
        message_text = prepare_broadcast_message(promo.text, apply_spintax=True, apply_jitter=True)
        message_text = parse_shortcodes_to_tg_emoji(message_text)

        try:
            entity = None

            # ── PRIORITY 1: Instant RAM lookup from pre-cached dialogs ──────────
            # Completely avoids ResolveUsernameRequest and bypasses username flood waits!
            if dialog_entities:
                cid = getattr(group, "chat_id", None)
                if cid:
                    entity = (
                        dialog_entities.get(cid)
                        or dialog_entities.get(abs(cid))
                        or dialog_entities.get(int(f"-100{abs(cid)}"))
                        or dialog_entities.get(-abs(cid))
                    )
                if not entity and identifier:
                    clean_id = str(identifier).strip().lower()
                    entity = dialog_entities.get(clean_id) or dialog_entities.get(clean_id.lstrip("@"))
                    if not entity and clean_id.lstrip("-").isdigit():
                        int_id = int(clean_id)
                        entity = dialog_entities.get(int_id) or dialog_entities.get(abs(int_id))

            # ── PRIORITY 2: Resolve by chat_id if not in dialog_entities ─────────
            if not entity and getattr(group, "chat_id", None):
                cid = group.chat_id
                for try_id in [int(f"-100{abs(cid)}"), cid, -abs(cid), abs(cid)]:
                    try:
                        entity = await client.get_entity(try_id)
                        if entity:
                            break
                    except Exception:
                        continue

            # ── PRIORITY 3: Fallback to identifier string resolution ─────────────
            if not entity:
                raw_id = str(identifier).strip()

                # Case 1: Already a proper negative Telegram ID (-100... or -...)
                if raw_id.startswith("-100") or (raw_id.startswith("-") and raw_id[1:].isdigit()):
                    try:
                        entity = await client.get_entity(int(raw_id))
                    except Exception as e_id:
                        return {"status": "error", "reason": f"Could not resolve chat ID {raw_id}: {e_id}"}

                # Case 2: Plain positive integer
                elif raw_id.isdigit():
                    resolved = False
                    for try_id in [int(f"-100{raw_id}"), -int(raw_id)]:
                        try:
                            entity = await client.get_entity(try_id)
                            resolved = True
                            break
                        except Exception:
                            continue
                    if not resolved:
                        return {"status": "error", "reason": f"Could not find any entity for ID '{raw_id}'"}

                # Case 3: @username
                elif raw_id.startswith("@"):
                    try:
                        entity = await client.get_entity(raw_id)
                    except FloodWaitError as efw:
                        return {"status": "flood_wait", "reason": f"Username lookup FloodWait: {efw.seconds}s", "seconds": efw.seconds}
                    except Exception:
                        try:
                            await client(JoinChannelRequest(raw_id.lstrip("@")))
                            entity = await client.get_entity(raw_id)
                        except FloodWaitError as efw:
                            return {"status": "flood_wait", "reason": f"Join FloodWait: {efw.seconds}s", "seconds": efw.seconds}
                        except Exception as ej:
                            return {"status": "error", "reason": f"Could not find or join group: {ej}"}

                # Case 4: invite link / username without @
                else:
                    parsed = extract_group_identifier(identifier)
                    if parsed["type"] == "username":
                        try:
                            entity = await client.get_entity(parsed["value"])
                        except FloodWaitError as efw:
                            return {"status": "flood_wait", "reason": f"Username FloodWait: {efw.seconds}s", "seconds": efw.seconds}
                        except Exception:
                            try:
                                await client(JoinChannelRequest(parsed["value"]))
                                entity = await client.get_entity(parsed["value"])
                            except FloodWaitError as efw:
                                return {"status": "flood_wait", "reason": f"Join FloodWait: {efw.seconds}s", "seconds": efw.seconds}
                            except Exception as ej:
                                return {"status": "error", "reason": f"Could not resolve group: {ej}"}
                    elif parsed["type"] == "invite_hash":
                        try:
                            res = await client(ImportChatInviteRequest(parsed["value"]))
                            if hasattr(res, "chats") and res.chats:
                                entity = res.chats[0]
                        except UserAlreadyParticipantError:
                            entity = await client.get_entity(identifier)
                        except FloodWaitError as efw:
                            return {"status": "flood_wait", "reason": f"Invite FloodWait: {efw.seconds}s", "seconds": efw.seconds}
                        except Exception as e_inv:
                            return {"status": "error", "reason": f"Private invite link expired or invalid: {e_inv}"}
                    else:
                        try:
                            entity = await client.get_entity(identifier)
                        except FloodWaitError as efw:
                            return {"status": "flood_wait", "reason": f"Entity FloodWait: {efw.seconds}s", "seconds": efw.seconds}
                        except Exception as e_raw:
                            return {"status": "error", "reason": f"Could not resolve entity: {e_raw}"}

            if not entity:
                return {"status": "error", "reason": "Could not locate group entity on Telegram"}

            # Check if it's a broadcast-only channel
            if isinstance(entity, Channel) and getattr(entity, "broadcast", False):
                return {"status": "forbidden", "reason": "Target is a Broadcast Channel (Admin post only)"}

            # Only attempt JoinChannelRequest if group was NOT already joined
            if not getattr(group, "is_joined", False):
                try:
                    await client(JoinChannelRequest(entity))
                except (UserAlreadyParticipantError, Exception):
                    pass

            sent = False
            if getattr(promo, "saved_msg_id", None):
                try:
                    saved_msg = await client.get_messages("me", ids=promo.saved_msg_id)
                    if saved_msg:
                        await client.send_message(entity, saved_msg)
                        sent = True
                except (
                    SlowModeWaitError,
                    ChatWriteForbiddenError,
                    UserBannedInChannelError,
                    ChatSendMediaForbiddenError,
                    ChannelPrivateError,
                    ChatAdminRequiredError,
                    PeerFloodError,
                    FloodWaitError,
                    AuthKeyUnregisteredError,
                    SessionRevokedError,
                    UserDeactivatedError,
                    UserDeactivatedBanError,
                ):
                    raise
                except Exception as e_saved:
                    logger.warning(f"Could not send Saved Message (id={promo.saved_msg_id}): {e_saved}. Falling back to standard send.")
                    sent = False

            if not sent:
                # Send message with media if attached and file exists
                has_media = (
                    promo.media_type in ("photo", "video")
                    and promo.media_path
                    and os.path.exists(promo.media_path)
                )

                try:
                    if has_media:
                        await client.send_file(
                            entity,
                            file=promo.media_path,
                            caption=message_text,
                            parse_mode="html",
                        )
                    else:
                        await client.send_message(
                            entity,
                            message_text,
                            parse_mode="html",
                            link_preview=True,
                        )
                except (
                    SlowModeWaitError,
                    ChatWriteForbiddenError,
                    UserBannedInChannelError,
                    ChatSendMediaForbiddenError,
                    ChannelPrivateError,
                    ChatAdminRequiredError,
                    PeerFloodError,
                    FloodWaitError,
                    AuthKeyUnregisteredError,
                    SessionRevokedError,
                    UserDeactivatedError,
                    UserDeactivatedBanError,
                ):
                    raise
                except Exception as e_html:
                    # If HTML parsing or entity formatting fails, retry as clean plain text
                    plain_msg = re.sub(r'<[^>]+>', '', message_text)
                    try:
                        if has_media:
                            await client.send_file(
                                entity,
                                file=promo.media_path,
                                caption=plain_msg,
                            )
                        else:
                            await client.send_message(
                                entity,
                                plain_msg,
                                link_preview=True,
                            )
                    except Exception as e_plain:
                        return {"status": "error", "reason": str(e_plain)}

            return {"status": "ok", "reason": "Sent successfully"}

        except SlowModeWaitError as e:
            return {"status": "slowmode", "reason": f"Slowmode active: wait {e.seconds}s", "seconds": e.seconds}

        except ChatWriteForbiddenError:
            try:
                await client(JoinChannelRequest(entity))
                if has_media:
                    await client.send_file(entity, file=promo.media_path, caption=message_text, parse_mode="html")
                else:
                    await client.send_message(entity, message_text, parse_mode="html", link_preview=True)
                return {"status": "ok", "reason": "Joined & Sent successfully"}
            except Exception as e_retry:
                return {"status": "forbidden", "reason": f"No permission to post: {e_retry}"}

        except UserBannedInChannelError as e_ban:
            msg = str(e_ban)
            if "banned from sending messages" in msg.lower():
                return {"status": "account_banned", "reason": msg}
            return {"status": "banned", "reason": "Account is banned/muted in this group"}

        except ChatSendMediaForbiddenError:
            try:
                await client.send_message(entity, message_text, parse_mode="html", link_preview=False)
                return {"status": "ok", "reason": "Sent as text fallback (Media Forbidden)"}
            except Exception as e2:
                return {"status": "forbidden", "reason": f"Media & Text forbidden: {e2}"}

        except ChannelPrivateError:
            return {"status": "private", "reason": "Group is private or account was kicked"}

        except ChatAdminRequiredError:
            return {"status": "forbidden", "reason": "Only admins can send messages"}

        except PeerFloodError:
            return {"status": "peer_flood", "reason": "Telegram PeerFlood triggered. Pausing worker."}

        except FloodWaitError as e:
            return {"status": "flood_wait", "reason": f"FloodWait: {e.seconds}s", "seconds": e.seconds}

        except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, UserDeactivatedBanError) as e:
            return {"status": "logged_out", "reason": f"Telegram session revoked or deactivated: {e}"}

        except Exception as e:
            return {"status": "error", "reason": str(e)}

    # ==================== MULTI-ACCOUNT WORKER RUNNER ====================

    async def start_account_broadcast(
        self,
        account_id: int,
        trigger_type: str = "MANUAL_ADMIN",
        selected_group_ids: list[int] | None = None,
    ) -> dict:
        """Launches an independent broadcast worker for a specific phone account.

        Args:
            account_id: DB id of the sender account.
            trigger_type: Label for what initiated the broadcast.
            selected_group_ids: Optional list of Group.id values to broadcast to.
                If provided, only those specific groups are targeted.
                If None, all selected groups for the account are fetched via
                ``get_selected_groups()``.
        """
        if self.is_account_broadcasting(account_id):
            return {"status": "already_running"}

        client = await tg_manager.get_client_for_account(account_id)
        if not client or not await client.is_user_authorized():
            return {"status": "not_authorized", "reason": "Sender account client not connected or unauthorized."}

        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)
            acc = next((a for a in accounts if a.id == account_id), None)
            if not acc:
                return {"status": "account_not_found"}

            # Fetch target groups — either explicit IDs or all selected for account
            if selected_group_ids is not None:
                from sqlalchemy import select as sa_select
                from database.models import Group
                result = await session.execute(
                    sa_select(Group).where(
                        Group.id.in_(selected_group_ids),
                        Group.account_id == account_id,
                        Group.status.in_(["ACTIVE", "SLOWMODE"]),
                    ).order_by(Group.id.asc())
                )
                target_groups = list(result.scalars().all())
            else:
                target_groups = await get_selected_groups(session, account_id)

            if not target_groups:
                return {"status": "no_groups"}

            promo = await get_or_create_account_promo(session, account_id, acc.phone)
            min_delay = int(await get_setting(session, "min_delay_sec", str(config.MIN_DELAY_PER_GROUP)))
            max_delay = int(await get_setting(session, "max_delay_sec", str(config.MAX_DELAY_PER_GROUP)))
            batch_size = int(await get_setting(session, "batch_size", str(config.BATCH_SIZE)))
            batch_cooldown = int(await get_setting(session, "batch_cooldown_sec", str(config.BATCH_COOLDOWN)))

            cycle = await create_cycle(session, len(target_groups), account_id=acc.id, account_phone=acc.phone)
            cycle_id = cycle.id

        worker_state = {
            "account_id": account_id,
            "account_phone": acc.phone,
            "sender_badge": f"@{acc.username or acc.first_name or acc.phone}",
            "cycle_id": cycle_id,
            "is_running": True,
            "is_paused": False,
            "should_stop": False,
            "current_index": 0,
            "total_targets": len(target_groups),
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "start_time": time.time(),
            "sent_groups_list": [],
            "failed_groups_list": [],
            "remaining_groups_list": [g.identifier for g in target_groups],
        }
        self.workers[account_id] = worker_state

        start_msg = (
            f"🚀 <b>Campaign Started for {acc.phone}</b> ({worker_state['sender_badge']})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Ad:</b> {promo.title}\n"
            f"🎯 <b>Total Target Groups:</b> {len(target_groups)}\n"
            f"⏱️ <b>Trigger:</b> {trigger_type}\n"
            f"🛡️ <b>Anti-Ban:</b> {min_delay}s–{max_delay}s Jitter + Spintax"
        )
        await self.notify_admins(start_msg)

        asyncio.create_task(
            self._run_worker_loop(
                account_id, client, promo, target_groups,
                min_delay, max_delay, batch_size, batch_cooldown,
            )
        )
        return {"status": "started", "cycle_id": cycle_id, "phone": acc.phone}

    async def _run_worker_loop(
        self, account_id, client, promo, target_groups,
        min_delay, max_delay, batch_size, batch_cooldown,
    ):
        w = self.workers.get(account_id)
        if not w:
            return

        sender_badge = w["sender_badge"]
        cycle_id = w["cycle_id"]

        # Pre-cache dialogs into Telethon in-memory cache so all chat IDs resolve locally in 0ms without hitting Telegram API
        dialog_entities = {}
        try:
            logger.info(f"Pre-caching dialogs for {w['account_phone']}...")
            dialogs = await client.get_dialogs(limit=None)
            for d in dialogs:
                if d.is_user:
                    continue
                ent = d.entity
                dialog_entities[d.id] = ent
                dialog_entities[abs(d.id)] = ent
                raw_cid = str(d.id).replace("-100", "").lstrip("-")
                if raw_cid.isdigit():
                    dialog_entities[int(raw_cid)] = ent
                uname = getattr(ent, "username", None)
                if uname:
                    dialog_entities[f"@{uname.lower()}"] = ent
                    dialog_entities[uname.lower()] = ent
            logger.info(f"Pre-cached {len(dialogs)} dialogs for {w['account_phone']} ({len(dialog_entities)} keys in RAM)")
        except Exception as e_dlg:
            logger.warning(f"Could not pre-cache dialogs for {w['account_phone']}: {e_dlg}")

        try:
            for idx, group in enumerate(target_groups, 1):
                while w.get("is_paused") and not w.get("should_stop"):
                    await asyncio.sleep(3)

                if w.get("should_stop") or not w.get("is_running"):
                    logger.info(f"Broadcast for {w['account_phone']} was stopped by Admin.")
                    break

                w["current_index"] = idx
                if group.identifier in w["remaining_groups_list"]:
                    w["remaining_groups_list"].remove(group.identifier)

                res = await self.send_to_single_group(client, group, promo, dialog_entities=dialog_entities)
                status = res.get("status")
                reason = res.get("reason", "Unknown")

                async with AsyncSessionLocal() as session:
                    if status == "ok":
                        w["success_count"] += 1
                        logger.info(f"[{w['account_phone']}] ✅ ({idx}/{w['total_targets']}) SENT: {group.identifier} ({group.title or ''})")
                        w["sent_groups_list"].append(group.identifier)
                        await update_group_status(session, group.id, "ACTIVE", is_success=True)
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "SENT")

                    elif status == "slowmode":
                        w["skipped_count"] += 1
                        sec = res.get("seconds", 60)
                        logger.info(f"[{w['account_phone']}] ⏳ ({idx}/{w['total_targets']}) SLOWMODE: {group.identifier} ({sec}s)")
                        w["failed_groups_list"].append({"identifier": group.identifier, "reason": f"Slowmode ({sec}s)"})
                        await update_group_status(session, group.id, "SLOWMODE", error=reason, slowmode_sec=sec)
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "SLOWMODE", reason)

                    elif status == "flood_wait":
                        wait_seconds = res.get("seconds", 60)
                        logger.warning(f"[{w['account_phone']}] ⚠️ ({idx}/{w['total_targets']}) FLOODWAIT: {group.identifier} ({wait_seconds}s)")

                        # If wait is longer than 5 minutes (e.g. 15 hours daily quota), don't freeze worker!
                        if wait_seconds > 300:
                            hours = round(wait_seconds / 3600, 1)
                            logger.warning(f"[{w['account_phone']}] 🛑 Telegram daily quota reached ({w['success_count']} delivered). Cooldown: {hours}h.")
                            await self.notify_admins(
                                f"⏳ <b>Daily Telegram Quota Reached ({w['account_phone']})</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🎉 Successfully delivered to <b>{w['success_count']} groups</b>!\n\n"
                                f"Telegram has set a cooldown of <b>{hours} hours</b> before this number can post to more groups.\n\n"
                                f"🛑 <i>Campaign ended cleanly to protect your account. You can switch to another phone number in the meantime!</i>"
                            )
                            w["failed_groups_list"].append({"identifier": group.identifier, "reason": f"Daily limit reached ({hours}h cooldown)"})
                            break

                        await self.notify_admins(
                            f"⏳ <b>Telegram FloodWait ({w['account_phone']}):</b> Pausing {wait_seconds}s..."
                        )
                        await asyncio.sleep(wait_seconds + 5)
                        res2 = await self.send_to_single_group(client, group, promo, dialog_entities=dialog_entities)
                        if res2.get("status") == "ok":
                            w["success_count"] += 1
                            logger.info(f"[{w['account_phone']}] ✅ ({idx}/{w['total_targets']}) SENT after FloodWait: {group.identifier}")
                            w["sent_groups_list"].append(group.identifier)
                            await update_group_status(session, group.id, "ACTIVE", is_success=True)
                            await log_broadcast_result(session, cycle_id, group.id, group.identifier, "SENT")
                        else:
                            w["failed_count"] += 1
                            logger.warning(f"[{w['account_phone']}] ❌ ({idx}/{w['total_targets']}) FAILED after FloodWait: {group.identifier} - {res2.get('reason')}")
                            w["failed_groups_list"].append({"identifier": group.identifier, "reason": res2.get("reason")})
                            await update_group_status(session, group.id, "RESTRICTED", error=res2.get("reason"))
                            await log_broadcast_result(session, cycle_id, group.id, group.identifier, "FAILED", res2.get("reason"))

                    elif status == "logged_out":
                        logger.error(f"[{w['account_phone']}] ❌ SESSION REVOKED/LOGGED OUT on Telegram!")
                        await update_sender_account_status(session, account_id, "NEED_LOGIN")
                        await self.notify_admins(
                            f"⚠️ <b>Account Logged Out:</b> {w['account_phone']} session was terminated on Telegram.\n"
                            "Please re-login via /menu ➡️ 📱 Phone Numbers & OTP."
                        )
                        break

                    elif status == "peer_flood":
                        w["failed_count"] += 1
                        logger.warning(f"[{w['account_phone']}] 🛡️ PEER FLOOD: {group.identifier}")
                        w["failed_groups_list"].append(
                            {"identifier": group.identifier, "reason": "Telegram Search Rate Limit (PeerFlood)"}
                        )
                        await log_broadcast_result(
                            session, cycle_id, group.id, group.identifier, "FAILED", "Telegram PeerFlood"
                        )
                        # Alert admin ONCE and safely stop worker to protect account from ban
                        await self.notify_admins(
                            f"🛡️ <b>Telegram Search Rate Limit Active ({w['account_phone']})</b>\n"
                            "Telegram has temporarily paused username searches for this account to prevent bans.\n\n"
                            "Worker paused safely. Please allow ~15 minutes before re-launching."
                        )
                        break

                    elif status == "account_banned" or "banned from sending messages" in reason.lower():
                        w["failed_count"] += 1
                        logger.error(f"[{w['account_phone']}] 🚨 ACCOUNT MUTED GLOBALLY BY TELEGRAM!")
                        w["failed_groups_list"].append(
                            {"identifier": group.identifier, "reason": "Muted Globally by Telegram (@SpamBot)"}
                        )
                        await log_broadcast_result(
                            session, cycle_id, group.id, group.identifier, "FAILED", "Muted Globally by Telegram (@SpamBot)"
                        )
                        await self.notify_admins(
                            f"🚨 <b>Telegram Account Muted ({w['account_phone']})</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            "Telegram has temporarily muted this number from sending messages in all public groups:\n\n"
                            f"<i>\"{reason}\"</i>\n\n"
                            "💡 <b>What to do:</b>\n"
                            "1. Open the Telegram app on this phone number.\n"
                            "2. Message <b>@SpamBot</b> to check when the mute will be lifted.\n"
                            "3. Broadcast using your other active number (<code>+918210411620</code>)!\n\n"
                            "🛑 <i>Campaign stopped automatically to protect your account.</i>"
                        )
                        break

                    elif status in ["forbidden", "banned", "private"]:
                        w["failed_count"] += 1
                        logger.warning(f"[{w['account_phone']}] 🚫 ({idx}/{w['total_targets']}) {status.upper()}: {group.identifier} - {reason}")
                        w["failed_groups_list"].append({"identifier": group.identifier, "reason": reason})
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "FAILED", reason)
                        # Mark as BANNED — don't delete so user can review the list
                        # Groups marked BANNED are auto-skipped in future broadcasts
                        await update_group_status(session, group.id, "BANNED", error=reason)

                    else:
                        w["failed_count"] += 1
                        logger.warning(f"[{w['account_phone']}] ❌ ({idx}/{w['total_targets']}) FAILED: {group.identifier} - {reason}")
                        w["failed_groups_list"].append({"identifier": group.identifier, "reason": reason})
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "FAILED", reason)
                        # Only permanently delete groups that are truly dead (NEVER on rate limits or floodwaits)
                        is_rate_limited = "wait" in reason.lower() or "flood" in reason.lower()
                        if not is_rate_limited and any(
                            err in reason
                            for err in [
                                "Cannot cast InputPeerUser",
                                "No user has",
                                "Nobody is using",
                                "expired or invalid",
                                "Could not find any entity for ID",
                            ]
                        ):
                            await delete_group(session, group.id)
                        else:
                            await update_group_status(session, group.id, "RESTRICTED", error=reason)

                # Batch cooldown & jitter
                if w["success_count"] > 0 and w["success_count"] % batch_size == 0 and idx < w["total_targets"]:
                    logger.info(f"Anti-ban batch cooldown for {w['account_phone']}: pausing {batch_cooldown}s...")
                    await asyncio.sleep(batch_cooldown)
                elif idx < w["total_targets"]:
                    if status == "ok":
                        sleep_sec = random.randint(min_delay, max_delay)
                    else:
                        sleep_sec = 2  # Fast skip on unsendable/dead links
                    await asyncio.sleep(sleep_sec)

        except Exception as e:
            logger.error(f"Fatal error in worker for {w['account_phone']}: {e}", exc_info=True)
            await self.notify_admins(f"❌ <b>Campaign Error ({w['account_phone']}):</b> {e}")

        finally:
            duration = int(time.time() - w["start_time"])
            mins = duration // 60
            secs = duration % 60
            final_status = (
                "COMPLETED"
                if w["current_index"] >= w["total_targets"]
                else ("STOPPED" if w["should_stop"] else "PAUSED")
            )

            async with AsyncSessionLocal() as session:
                await finish_cycle(
                    session,
                    cycle_id,
                    final_status,
                    w["success_count"],
                    w["failed_count"],
                    w["skipped_count"],
                    duration,
                )
                try:
                    promo_db = await get_or_create_account_promo(session, account_id)
                    promo_db.last_run_at = datetime.datetime.utcnow()
                    await session.commit()
                    logger.info(f"Broadcast ended for {w['account_phone']}: updated last_run_at=NOW.")
                except Exception as ex_p:
                    logger.warning(f"Could not update last_run_at for {w['account_phone']}: {ex_p}")

            report = self._generate_worker_summary(w, mins, secs, final_status)
            await self.notify_admins(report)

            w["is_running"] = False
            w["is_paused"] = False
            w["should_stop"] = False

    def _generate_worker_summary(self, w: dict, mins: int, secs: int, status: str) -> str:
        remaining_count = len(w["remaining_groups_list"])
        sent_samples = [f"• <code>{g}</code>" for g in w["sent_groups_list"][:5]]
        sent_text = "\n".join(sent_samples) if sent_samples else "<i>None</i>"
        if len(w["sent_groups_list"]) > 5:
            sent_text += f"\n<i>...and {len(w['sent_groups_list']) - 5} more sent.</i>"

        failed_samples = [
            f"• <b>{f['identifier']}</b>: <code>{f['reason']}</code>"
            for f in w["failed_groups_list"][:5]
        ]
        failed_text = "\n".join(failed_samples) if failed_samples else "<i>None</i>"
        if len(w["failed_groups_list"]) > 5:
            failed_text += f"\n<i>...and {len(w['failed_groups_list']) - 5} more failed.</i>"

        status_emoji = "🛑 STOPPED" if status == "STOPPED" else "🎉 COMPLETED"

        return (
            f"📊 <b>CAMPAIGN SUMMARY — {w['account_phone']} ({status_emoji})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 <b>Sender:</b> {w['sender_badge']}\n"
            f"⏱️ <b>Duration:</b> {mins}m {secs}s\n"
            f"🎯 <b>Total Targets:</b> {w['total_targets']}\n\n"
            f"📈 <b>Results:</b>\n"
            f"• ✅ <b>Delivered Successfully:</b> <code>{w['success_count']} groups</code>\n"
            f"• ❌ <b>Failed / Banned:</b> <code>{w['failed_count']} groups</code>\n"
            f"• ⏳ <b>Slowmode Skipped:</b> <code>{w['skipped_count']} groups</code>\n"
            f"• ⏸️ <b>Remaining:</b> <code>{remaining_count} groups</code>\n\n"
            f"✅ <b>Delivered Sample:</b>\n{sent_text}\n\n"
            f"⚠️ <b>Failed Sample:</b>\n{failed_text}\n\n"
            f"🛡️ <i>Your account is safe. Detailed logs saved in /menu.</i>"
        )

    # ==================== GLOBAL MULTI-CAMPAIGN CONTROLS ====================

    async def start_all_campaigns(self, trigger_type: str = "MANUAL_ALL") -> dict:
        """Launches all connected accounts simultaneously in parallel!"""
        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)

        if not accounts:
            return {"status": "no_accounts", "started": 0}

        started = 0
        for acc in accounts:
            res = await self.start_account_broadcast(acc.id, trigger_type=trigger_type)
            if res.get("status") == "started":
                started += 1

        return {"status": "ok", "started": started, "total_accounts": len(accounts)}

    def stop_account_broadcast(self, account_id: int):
        if account_id in self.workers:
            self.workers[account_id]["should_stop"] = True
            self.workers[account_id]["is_running"] = False

    def pause_account_broadcast(self, account_id: int):
        if account_id in self.workers:
            self.workers[account_id]["is_paused"] = True

    def resume_account_broadcast(self, account_id: int):
        if account_id in self.workers:
            self.workers[account_id]["is_paused"] = False

    def stop_all_campaigns(self):
        for w in self.workers.values():
            w["should_stop"] = True
            w["is_running"] = False
            w["is_paused"] = False

    def stop_broadcast(self):
        self.stop_all_campaigns()

    def pause_broadcast(self):
        for w in self.workers.values():
            w["is_paused"] = True

    def resume_broadcast(self):
        for w in self.workers.values():
            w["is_paused"] = False

    async def execute_broadcast_round(self, trigger_type: str = "SCHEDULED") -> dict:
        """Default scheduled trigger: runs all connected accounts in parallel."""
        return await self.start_all_campaigns(trigger_type=trigger_type)


broadcaster = SafeBroadcaster()
