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
        self.is_broadcasting = False
        self.is_paused = False
        self.should_stop = False
        self.current_cycle_id = None
        self.current_index = 0
        self.total_targets = 0
        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.start_time = 0
        self.sent_groups_list = []
        self.failed_groups_list = []
        self.remaining_groups_list = []
        self.bot_instance = None  # Reference to Aiogram Bot to send notifications

    def set_bot_instance(self, bot):
        self.bot_instance = bot

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

    def get_progress_status(self) -> dict:
        if not self.is_broadcasting:
            return {"is_running": False}

        elapsed = int(time.time() - self.start_time)
        remaining = max(0, self.total_targets - self.current_index)
        return {
            "is_running": True,
            "is_paused": self.is_paused,
            "cycle_id": self.current_cycle_id,
            "current_index": self.current_index,
            "total_targets": self.total_targets,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "remaining_count": remaining,
            "elapsed_seconds": elapsed,
            "progress_percent": round((self.current_index / max(self.total_targets, 1)) * 100, 1)
        }

    async def send_to_single_group(self, client: TelegramClient, group, promo) -> dict:
        await tg_manager.ensure_connected()
        client = tg_manager.client or client
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
                    # Try joining public channel/group first if not found
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

            # If it's a broadcast-only channel, regular users cannot post
            from telethon.tl.types import Channel
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.errors import UserAlreadyParticipantError

            if isinstance(entity, Channel) and getattr(entity, 'broadcast', False):
                return {"status": "forbidden", "reason": "Target is a Broadcast Channel (Admin post only)"}

            # Ensure we are joined before sending
            try:
                await client(JoinChannelRequest(entity))
            except (UserAlreadyParticipantError, Exception):
                pass

            # Send message
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
            # Try joining explicitly and retry once
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
            return {"status": "peer_flood", "reason": "Telegram PeerFlood triggered. Pausing broadcast."}

        except FloodWaitError as e:
            return {"status": "flood_wait", "reason": f"FloodWait: {e.seconds}s", "seconds": e.seconds}

        except Exception as e:
            return {"status": "error", "reason": str(e)}

    async def execute_broadcast_round(self, trigger_type: str = "SCHEDULED") -> dict:
        if self.is_broadcasting:
            logger.warning("Broadcast round is already running! Skipping duplicate trigger.")
            return {"status": "already_running"}

        await tg_manager.ensure_connected()
        client = tg_manager.client
        if not client or not tg_manager.is_connected:
            msg = "⚠️ <b>Broadcast Skipped:</b> No active Telegram sender account connected. Please login in /menu."
            logger.warning(msg)
            await self.notify_admins(msg)
            return {"status": "not_authorized"}

        me = await tg_manager.get_me()
        sender_badge = f"@{me.username or me.first_name}" if me else "Sender Account"

        async with AsyncSessionLocal() as session:
            is_enabled = await get_setting(session, "broadcast_enabled", "true")
            if is_enabled.lower() != "true" and trigger_type == "SCHEDULED":
                logger.info("Broadcasting is disabled in settings.")
                return {"status": "disabled"}

            target_groups = await get_active_groups(session)
            if not target_groups:
                logger.info("No active groups found.")
                await self.notify_admins("⚠️ <b>Broadcast Skipped:</b> No active target groups found. Add groups using /menu.")
                return {"status": "no_groups"}

            promo = await get_active_promo_message(session)
            min_delay = int(await get_setting(session, "min_delay_sec", str(config.MIN_DELAY_PER_GROUP)))
            max_delay = int(await get_setting(session, "max_delay_sec", str(config.MAX_DELAY_PER_GROUP)))
            batch_size = int(await get_setting(session, "batch_size", str(config.BATCH_SIZE)))
            batch_cooldown = int(await get_setting(session, "batch_cooldown_sec", str(config.BATCH_COOLDOWN)))

            cycle = await create_cycle(session, len(target_groups))
            self.current_cycle_id = cycle.id

        self.is_broadcasting = True
        self.is_paused = False
        self.should_stop = False
        self.total_targets = len(target_groups)
        self.current_index = 0
        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.start_time = time.time()
        self.sent_groups_list = []
        self.failed_groups_list = []
        self.remaining_groups_list = [g.identifier for g in target_groups]

        start_msg = (
            f"🚀 <b>Broadcast Cycle #{self.current_cycle_id} Started</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 <b>Sender Account:</b> {sender_badge}\n"
            f"🎯 <b>Total Target Groups:</b> {self.total_targets}\n"
            f"⏱️ <b>Trigger:</b> {trigger_type}\n"
            f"🛡️ <b>Anti-Ban Protection:</b> {min_delay}s–{max_delay}s Jitter + Anti-Hash Spintax"
        )
        await self.notify_admins(start_msg)

        try:
            for idx, group in enumerate(target_groups, 1):
                while self.is_paused:
                    await asyncio.sleep(3)
                
                if self.should_stop or not self.is_broadcasting:
                    logger.info("Broadcast was stopped manually by Admin.")
                    break

                self.current_index = idx
                if group.identifier in self.remaining_groups_list:
                    self.remaining_groups_list.remove(group.identifier)

                res = await self.send_to_single_group(client, group, promo)
                status = res.get("status")
                reason = res.get("reason", "Unknown")

                async with AsyncSessionLocal() as session:
                    if status == "ok":
                        self.success_count += 1
                        self.sent_groups_list.append(group.identifier)
                        await update_group_status(session, group.id, "ACTIVE", is_success=True)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "SENT")
                    elif status == "slowmode":
                        self.skipped_count += 1
                        sec = res.get("seconds", 60)
                        self.failed_groups_list.append({"identifier": group.identifier, "reason": f"Slowmode ({sec}s)"})
                        await update_group_status(session, group.id, "SLOWMODE", error=reason, slowmode_sec=sec)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "SLOWMODE", reason)
                    elif status == "flood_wait":
                        wait_seconds = res.get("seconds", 60)
                        await self.notify_admins(f"⏳ <b>Telegram FloodWait:</b> Pausing {wait_seconds}s to protect {sender_badge}...")
                        await asyncio.sleep(wait_seconds + 5)
                        # Retry once
                        res2 = await self.send_to_single_group(client, group, promo)
                        if res2.get("status") == "ok":
                            self.success_count += 1
                            self.sent_groups_list.append(group.identifier)
                            await update_group_status(session, group.id, "ACTIVE", is_success=True)
                            await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "SENT")
                        else:
                            self.failed_count += 1
                            self.failed_groups_list.append({"identifier": group.identifier, "reason": res2.get("reason")})
                            await update_group_status(session, group.id, "RESTRICTED", error=res2.get("reason"))
                            await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", res2.get("reason"))
                    elif status == "peer_flood":
                        self.failed_count += 1
                        self.failed_groups_list.append({"identifier": group.identifier, "reason": reason})
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", reason)
                        await self.notify_admins(f"⚠️ <b>PEER FLOOD DETECTED:</b> Halting round early to safeguard {sender_badge}!")
                        break
                    elif status in ["forbidden", "banned", "private"]:
                        self.failed_count += 1
                        self.failed_groups_list.append({"identifier": group.identifier, "reason": reason})
                        db_status = "BANNED" if status == "banned" else "RESTRICTED"
                        await update_group_status(session, group.id, db_status, error=reason)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", reason)
                    else:
                        self.failed_count += 1
                        self.failed_groups_list.append({"identifier": group.identifier, "reason": reason})
                        await update_group_status(session, group.id, "RESTRICTED", error=reason)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", reason)

                # Batch cooldown & jitter
                if idx % batch_size == 0 and idx < self.total_targets:
                    logger.info(f"Anti-ban batch cooldown: pausing {batch_cooldown}s after {idx} groups...")
                    await asyncio.sleep(batch_cooldown)
                elif idx < self.total_targets:
                    sleep_sec = random.randint(min_delay, max_delay)
                    await asyncio.sleep(sleep_sec)

        except Exception as e:
            logger.error(f"Fatal error during broadcast loop: {e}", exc_info=True)
            await self.notify_admins(f"❌ <b>Broadcast Error:</b> {e}")

        finally:
            duration = int(time.time() - self.start_time)
            mins = duration // 60
            secs = duration % 60
            final_status = "COMPLETED" if self.current_index >= self.total_targets else ("STOPPED" if self.should_stop else "PAUSED")

            async with AsyncSessionLocal() as session:
                await finish_cycle(
                    session,
                    self.current_cycle_id,
                    final_status,
                    self.success_count,
                    self.failed_count,
                    self.skipped_count,
                    duration
                )

            # Send Detailed Completion / Stop Breakdown
            report = self.generate_detailed_summary_report(mins, secs, final_status, sender_badge)
            await self.notify_admins(report)

            self.is_broadcasting = False
            self.is_paused = False
            self.should_stop = False

        return {
            "cycle_id": self.current_cycle_id,
            "status": final_status,
            "sent": self.success_count,
            "failed": self.failed_count,
            "remaining": len(self.remaining_groups_list),
            "duration_min": mins
        }

    def generate_detailed_summary_report(self, mins: int, secs: int, status: str, sender: str) -> str:
        remaining_count = len(self.remaining_groups_list)
        
        # Sent samples
        sent_samples = [f"• <code>{g}</code>" for g in self.sent_groups_list[:6]]
        sent_text = "\n".join(sent_samples) if sent_samples else "<i>None</i>"
        if len(self.sent_groups_list) > 6:
            sent_text += f"\n<i>...and {len(self.sent_groups_list) - 6} more sent successfully.</i>"

        # Failed samples
        failed_samples = [f"• <b>{f['identifier']}</b>: <code>{f['reason']}</code>" for f in self.failed_groups_list[:6]]
        failed_text = "\n".join(failed_samples) if failed_samples else "<i>None</i>"
        if len(self.failed_groups_list) > 6:
            failed_text += f"\n<i>...and {len(self.failed_groups_list) - 6} more failed.</i>"

        # Remaining samples
        rem_samples = [f"• <code>{g}</code>" for g in self.remaining_groups_list[:5]]
        rem_text = "\n".join(rem_samples) if rem_samples else "<i>0 remaining (All processed)</i>"
        if remaining_count > 5:
            rem_text += f"\n<i>...and {remaining_count - 5} more pending.</i>"

        status_emoji = "🛑 STOPPED" if status == "STOPPED" else "🎉 COMPLETED"

        report = (
            f"📊 <b>BROADCAST SUMMARY — CYCLE #{self.current_cycle_id} ({status_emoji})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 <b>Sender Account:</b> {sender}\n"
            f"⏱️ <b>Time Elapsed:</b> {mins}m {secs}s\n"
            f"🎯 <b>Total Groups Targeted:</b> {self.total_targets}\n\n"
            f"📈 <b>Performance Metrics:</b>\n"
            f"• ✅ <b>Delivered Successfully:</b> <code>{self.success_count} groups</code>\n"
            f"• ❌ <b>Failed / Banned:</b> <code>{self.failed_count} groups</code>\n"
            f"• ⏳ <b>Slowmode Skipped:</b> <code>{self.skipped_count} groups</code>\n"
            f"• ⏸️ <b>Remaining / Unsent:</b> <code>{remaining_count} groups</code>\n\n"
            f"✅ <b>Delivered Groups Sample:</b>\n{sent_text}\n\n"
            f"⚠️ <b>Failed Groups & Reasons:</b>\n{failed_text}\n\n"
            f"📋 <b>Remaining Groups:</b>\n{rem_text}\n\n"
            "🛡️ <i>Your account remains safe & protected. Full logs stored in /menu.</i>"
        )
        return report

    def stop_broadcast(self):
        self.should_stop = True
        self.is_broadcasting = False
        self.is_paused = False

    def pause_broadcast(self):
        self.is_paused = True

    def resume_broadcast(self):
        self.is_paused = False

broadcaster = SafeBroadcaster()
