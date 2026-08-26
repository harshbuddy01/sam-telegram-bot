import asyncio
import random
import time
import datetime
import logging
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    SlowModeWaitError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatSendMediaForbiddenError,
    PeerFloodError
)
from core.client import tg_manager
from utils.spintax import prepare_broadcast_message
from utils.premium_emojis import parse_shortcodes_to_tg_emoji
from database.database import AsyncSessionLocal
from database.crud import (
    get_active_groups,
    get_active_promo_message,
    get_or_create_account_promo,
    get_all_sender_accounts,
    get_active_sender_account,
    update_group_status,
    create_cycle,
    finish_cycle,
    log_broadcast_result,
    get_setting
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
                    disable_web_page_preview=True
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
            "progress_percent": round((curr / max(total, 1)) * 100, 1)
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
                "progress_percent": round((w.get("current_index", 0) / max(w.get("total_targets", 1), 1)) * 100, 1)
            })
        return results

    async def send_to_single_group(self, client: TelegramClient, group, promo) -> dict:
        identifier = group.identifier
        
        # Prepare unique anti-hash Spintax variation
        message_text = prepare_broadcast_message(promo.text, apply_spintax=True, apply_jitter=True)
        message_text = parse_shortcodes_to_tg_emoji(message_text)

        try:
            # Resolve entity (with auto-join support for unjoined groups)
            entity = None
            if str(identifier).startswith("-100") or (str(identifier).startswith("-") and str(identifier)[1:].isdigit()):
                entity = await client.get_entity(int(identifier))
            elif identifier.startswith("@"):
                try:
                    entity = await client.get_entity(identifier)
                except Exception:
                    from telethon.tl.functions.channels import JoinChannelRequest
                    try:
                        await client(JoinChannelRequest(identifier.lstrip("@")))
                        entity = await client.get_entity(identifier)
                    except Exception as ej:
                        return {"status": "error", "reason": f"Could not find or join group: {ej}"}
            else:
                from core.joiner import extract_group_identifier
                parsed = extract_group_identifier(identifier)
                if parsed["type"] == "username":
                    try:
                        entity = await client.get_entity(parsed["value"])
                    except Exception:
                        from telethon.tl.functions.channels import JoinChannelRequest
                        try:
                            await client(JoinChannelRequest(parsed["value"]))
                            entity = await client.get_entity(parsed["value"])
                        except Exception as ej:
                            return {"status": "error", "reason": f"Could not resolve group: {ej}"}
                elif parsed["type"] == "invite_hash":
                    from telethon.tl.functions.messages import ImportChatInviteRequest
                    from telethon.errors import UserAlreadyParticipantError
                    try:
                        res = await client(ImportChatInviteRequest(parsed["value"]))
                        if hasattr(res, 'chats') and res.chats:
                            entity = res.chats[0]
                    except UserAlreadyParticipantError:
                        entity = await client.get_entity(identifier)
                    except Exception as e_inv:
                        return {"status": "error", "reason": f"Private invite link expired or invalid: {e_inv}"}
                else:
                    try:
                        entity = await client.get_entity(identifier)
                    except Exception as e_raw:
                        return {"status": "error", "reason": f"Could not resolve entity: {e_raw}"}

            if not entity:
                return {"status": "error", "reason": "Could not locate group entity on Telegram"}

            # Check if it's a broadcast-only channel
            from telethon.tl.types import Channel
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.errors import UserAlreadyParticipantError

            if isinstance(entity, Channel) and getattr(entity, 'broadcast', False):
                return {"status": "forbidden", "reason": "Target is a Broadcast Channel (Admin post only)"}

            # Ensure membership before sending
            try:
                await client(JoinChannelRequest(entity))
            except (UserAlreadyParticipantError, Exception):
                pass

            # Send message with media if attached
            if promo.media_type == "photo" and promo.media_path:
                await client.send_file(
                    entity,
                    file=promo.media_path,
                    caption=message_text,
                    parse_mode="html"
                )
            elif promo.media_type == "video" and promo.media_path:
                await client.send_file(
                    entity,
                    file=promo.media_path,
                    caption=message_text,
                    parse_mode="html"
                )
            else:
                await client.send_message(
                    entity,
                    message_text,
                    parse_mode="html",
                    link_preview=True
                )

            return {"status": "ok", "reason": "Sent successfully"}

        except SlowModeWaitError as e:
            return {"status": "slowmode", "reason": f"Slowmode active: wait {e.seconds}s", "seconds": e.seconds}

        except ChatWriteForbiddenError:
            try:
                from telethon.tl.functions.channels import JoinChannelRequest
                await client(JoinChannelRequest(entity))
                if promo.media_type == "photo" and promo.media_path:
                    await client.send_file(entity, file=promo.media_path, caption=message_text, parse_mode="html")
                elif promo.media_type == "video" and promo.media_path:
                    await client.send_file(entity, file=promo.media_path, caption=message_text, parse_mode="html")
                else:
                    await client.send_message(entity, message_text, parse_mode="html", link_preview=True)
                return {"status": "ok", "reason": "Joined & Sent successfully"}
            except Exception as e_retry:
                return {"status": "forbidden", "reason": f"No permission to post: {e_retry}"}

        except UserBannedInChannelError:
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

        except Exception as e:
            return {"status": "error", "reason": str(e)}

    # ==================== MULTI-ACCOUNT WORKER RUNNER ====================

    async def start_account_broadcast(self, account_id: int, trigger_type: str = "MANUAL_ADMIN") -> dict:
        """Launches an independent broadcast worker for a specific phone account."""
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

            target_groups = await get_active_groups(session)
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
            "remaining_groups_list": [g.identifier for g in target_groups]
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
            self._run_worker_loop(account_id, client, promo, target_groups, min_delay, max_delay, batch_size, batch_cooldown)
        )
        return {"status": "started", "cycle_id": cycle_id, "phone": acc.phone}

    async def _run_worker_loop(self, account_id, client, promo, target_groups, min_delay, max_delay, batch_size, batch_cooldown):
        w = self.workers.get(account_id)
        if not w:
            return

        sender_badge = w["sender_badge"]
        cycle_id = w["cycle_id"]

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

                res = await self.send_to_single_group(client, group, promo)
                status = res.get("status")
                reason = res.get("reason", "Unknown")

                async with AsyncSessionLocal() as session:
                    if status == "ok":
                        w["success_count"] += 1
                        w["sent_groups_list"].append(group.identifier)
                        await update_group_status(session, group.id, "ACTIVE", is_success=True)
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "SENT")
                    elif status == "slowmode":
                        w["skipped_count"] += 1
                        sec = res.get("seconds", 60)
                        w["failed_groups_list"].append({"identifier": group.identifier, "reason": f"Slowmode ({sec}s)"})
                        await update_group_status(session, group.id, "SLOWMODE", error=reason, slowmode_sec=sec)
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "SLOWMODE", reason)
                    elif status == "flood_wait":
                        wait_seconds = res.get("seconds", 60)
                        await self.notify_admins(f"⏳ <b>Telegram FloodWait ({w['account_phone']}):</b> Pausing {wait_seconds}s...")
                        await asyncio.sleep(wait_seconds + 5)
                        res2 = await self.send_to_single_group(client, group, promo)
                        if res2.get("status") == "ok":
                            w["success_count"] += 1
                            w["sent_groups_list"].append(group.identifier)
                            await update_group_status(session, group.id, "ACTIVE", is_success=True)
                            await log_broadcast_result(session, cycle_id, group.id, group.identifier, "SENT")
                        else:
                            w["failed_count"] += 1
                            w["failed_groups_list"].append({"identifier": group.identifier, "reason": res2.get("reason")})
                            await update_group_status(session, group.id, "RESTRICTED", error=res2.get("reason"))
                            await log_broadcast_result(session, cycle_id, group.id, group.identifier, "FAILED", res2.get("reason"))
                    elif status == "peer_flood":
                        w["failed_count"] += 1
                        w["failed_groups_list"].append({"identifier": group.identifier, "reason": reason})
                        await update_group_status(session, group.id, "INVALID_LINK", error=reason)
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "FAILED", reason)
                        await self.notify_admins(f"⏳ <b>Telegram Search Rate Limit ({w['account_phone']}):</b> Pausing 90s for safety, then resuming automatically...")
                        await asyncio.sleep(90)
                    elif status in ["forbidden", "banned", "private"]:
                        w["failed_count"] += 1
                        w["failed_groups_list"].append({"identifier": group.identifier, "reason": reason})
                        db_status = "BANNED" if status == "banned" else "RESTRICTED"
                        await update_group_status(session, group.id, db_status, error=reason)
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "FAILED", reason)
                    else:
                        w["failed_count"] += 1
                        w["failed_groups_list"].append({"identifier": group.identifier, "reason": reason})
                        await update_group_status(session, group.id, "RESTRICTED", error=reason)
                        await log_broadcast_result(session, cycle_id, group.id, group.identifier, "FAILED", reason)

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
            final_status = "COMPLETED" if w["current_index"] >= w["total_targets"] else ("STOPPED" if w["should_stop"] else "PAUSED")

            async with AsyncSessionLocal() as session:
                await finish_cycle(
                    session,
                    cycle_id,
                    final_status,
                    w["success_count"],
                    w["failed_count"],
                    w["skipped_count"],
                    duration
                )

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

        failed_samples = [f"• <b>{f['identifier']}</b>: <code>{f['reason']}</code>" for f in w["failed_groups_list"][:5]]
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

