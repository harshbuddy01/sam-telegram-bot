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
        self.current_cycle_id = None
        self.current_index = 0
        self.total_targets = 0
        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.start_time = 0
        self.last_error_alert = ""
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
        return {
            "is_running": True,
            "is_paused": self.is_paused,
            "cycle_id": self.current_cycle_id,
            "current_index": self.current_index,
            "total_targets": self.total_targets,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "elapsed_seconds": elapsed,
            "progress_percent": round((self.current_index / max(self.total_targets, 1)) * 100, 1)
        }

    async def send_to_single_group(self, client: TelegramClient, group, promo) -> dict:
        """
        Sends the promotion message to a single group with anti-ban protections.
        """
        identifier = group.identifier
        
        # 1. Prepare unique anti-hash Spintax variation of promo message
        message_text = prepare_broadcast_message(promo.text, apply_spintax=True, apply_jitter=True)
        message_text = parse_shortcodes_to_tg_emoji(message_text)

        try:
            # Resolve entity
            entity = None
            if str(identifier).startswith("-100") or (str(identifier).startswith("-") and str(identifier)[1:].isdigit()):
                entity = await client.get_entity(int(identifier))
            elif identifier.startswith("@") or not identifier.startswith("http"):
                entity = await client.get_entity(identifier)
            else:
                from core.joiner import extract_group_identifier
                parsed = extract_group_identifier(identifier)
                if parsed["type"] == "username":
                    entity = await client.get_entity(parsed["value"])
                else:
                    return {"status": "error", "reason": "Invite link format - must be joined first"}

            # Send message based on media type
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
            logger.warning(f"Slowmode active in {identifier}: wait {e.seconds}s")
            return {"status": "slowmode", "reason": f"Slowmode active: {e.seconds}s", "seconds": e.seconds}

        except ChatWriteForbiddenError:
            logger.warning(f"Posting forbidden in {identifier}")
            return {"status": "forbidden", "reason": "No permission to send messages (ChatWriteForbidden)"}

        except UserBannedInChannelError:
            logger.warning(f"Account banned or muted in {identifier}")
            return {"status": "banned", "reason": "Account is banned/muted in this group"}

        except ChatSendMediaForbiddenError:
            logger.warning(f"Media forbidden in {identifier}, trying text fallback...")
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
            logger.error("Telegram PeerFloodError triggered! Too many requests.")
            return {"status": "peer_flood", "reason": "Telegram PeerFlood triggered. Pausing broadcast."}

        except FloodWaitError as e:
            logger.warning(f"Telegram FloodWaitError: wait {e.seconds}s")
            return {"status": "flood_wait", "reason": f"FloodWait: {e.seconds}s", "seconds": e.seconds}

        except Exception as e:
            logger.error(f"Failed to send to {identifier}: {e}")
            return {"status": "error", "reason": str(e)}

    async def execute_broadcast_round(self, trigger_type: str = "SCHEDULED"):
        """
        Main execution loop for a full broadcasting cycle across all target groups.
        """
        if self.is_broadcasting:
            logger.warning("Broadcast round is already running! Skipping duplicate trigger.")
            return

        client = tg_manager.client
        if not client or not tg_manager.is_connected:
            msg = "⚠️ <b>Broadcast Skipped:</b> Userbot sender client is not connected or authorized. Please login first."
            logger.warning(msg)
            await self.notify_admins(msg)
            return

        async with AsyncSessionLocal() as session:
            # Check if broadcast is enabled
            is_enabled = await get_setting(session, "broadcast_enabled", "true")
            if is_enabled.lower() != "true" and trigger_type == "SCHEDULED":
                logger.info("Broadcasting is currently disabled by Admin in settings.")
                return

            target_groups = await get_active_groups(session)
            if not target_groups:
                logger.info("No active groups found to broadcast to.")
                await self.notify_admins("⚠️ <b>Broadcast Skipped:</b> No active target groups found. Add groups using /menu.")
                return

            promo = await get_active_promo_message(session)
            
            # Anti-ban dynamic settings
            min_delay = int(await get_setting(session, "min_delay_sec", str(config.MIN_DELAY_PER_GROUP)))
            max_delay = int(await get_setting(session, "max_delay_sec", str(config.MAX_DELAY_PER_GROUP)))
            batch_size = int(await get_setting(session, "batch_size", str(config.BATCH_SIZE)))
            batch_cooldown = int(await get_setting(session, "batch_cooldown_sec", str(config.BATCH_COOLDOWN)))

            # Initialize Cycle
            cycle = await create_cycle(session, len(target_groups))
            self.current_cycle_id = cycle.id

        self.is_broadcasting = True
        self.is_paused = False
        self.total_targets = len(target_groups)
        self.current_index = 0
        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.start_time = time.time()

        start_msg = (
            f"🚀 <b>Broadcast Cycle #{self.current_cycle_id} Started</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Total Target Groups:</b> {self.total_targets}\n"
            f"⏱️ <b>Trigger:</b> {trigger_type}\n"
            f"🛡️ <b>Anti-Ban Delay:</b> {min_delay}s - {max_delay}s per group\n"
            f"☕ <b>Batch Cooldown:</b> {batch_cooldown}s every {batch_size} groups"
        )
        await self.notify_admins(start_msg)

        failed_details = []

        try:
            for idx, group in enumerate(target_groups, 1):
                while self.is_paused:
                    await asyncio.sleep(5)
                
                if not self.is_broadcasting:
                    logger.info("Broadcast was stopped manually by Admin.")
                    break

                self.current_index = idx

                # Send
                res = await self.send_to_single_group(client, group, promo)
                status = res.get("status")
                reason = res.get("reason", "Unknown")

                async with AsyncSessionLocal() as session:
                    if status == "ok":
                        self.success_count += 1
                        await update_group_status(session, group.id, "ACTIVE", is_success=True)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "SENT")
                    elif status == "slowmode":
                        self.skipped_count += 1
                        sec = res.get("seconds", 60)
                        await update_group_status(session, group.id, "SLOWMODE", error=reason, slowmode_sec=sec)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "SLOWMODE", reason)
                        failed_details.append(f"• <b>{group.identifier}</b>: Slowmode ({sec}s)")
                    elif status == "flood_wait":
                        wait_seconds = res.get("seconds", 60)
                        logger.warning(f"Telegram FloodWait: sleeping {wait_seconds}s...")
                        await self.notify_admins(f"⏳ <b>Telegram FloodWait:</b> Pausing for {wait_seconds}s to protect your account...")
                        await asyncio.sleep(wait_seconds + 5)
                        # Retry once after sleep
                        res2 = await self.send_to_single_group(client, group, promo)
                        if res2.get("status") == "ok":
                            self.success_count += 1
                            await update_group_status(session, group.id, "ACTIVE", is_success=True)
                            await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "SENT")
                        else:
                            self.failed_count += 1
                            await update_group_status(session, group.id, "RESTRICTED", error=res2.get("reason"))
                            await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", res2.get("reason"))
                            failed_details.append(f"• <b>{group.identifier}</b>: {res2.get('reason')}")
                    elif status == "peer_flood":
                        self.failed_count += 1
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", reason)
                        await self.notify_admins("⚠️ <b>PEER FLOOD DETECTED:</b> Halting current broadcast cycle early to safeguard your phone number!")
                        break
                    elif status in ["forbidden", "banned", "private"]:
                        self.failed_count += 1
                        db_status = "BANNED" if status == "banned" else "RESTRICTED"
                        await update_group_status(session, group.id, db_status, error=reason)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", reason)
                        failed_details.append(f"• <b>{group.identifier}</b>: {reason}")
                    else:
                        self.failed_count += 1
                        await update_group_status(session, group.id, "RESTRICTED", error=reason)
                        await log_broadcast_result(session, self.current_cycle_id, group.id, group.identifier, "FAILED", reason)
                        failed_details.append(f"• <b>{group.identifier}</b>: {reason}")

                # Anti-ban batch cooldown pause
                if idx % batch_size == 0 and idx < self.total_targets:
                    logger.info(f"Anti-ban batch cooldown: pausing {batch_cooldown}s after {idx} groups...")
                    await asyncio.sleep(batch_cooldown)
                elif idx < self.total_targets:
                    # Random jitter sleep between groups
                    sleep_sec = random.randint(min_delay, max_delay)
                    await asyncio.sleep(sleep_sec)

        except Exception as e:
            logger.error(f"Fatal error during broadcast loop: {e}", exc_info=True)
            await self.notify_admins(f"❌ <b>Broadcast Error:</b> {e}")

        finally:
            duration = int(time.time() - self.start_time)
            mins = duration // 60
            secs = duration % 60
            final_status = "COMPLETED" if self.current_index >= self.total_targets else "PAUSED"

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

            # Build comprehensive report
            failed_snippet = ""
            if failed_details:
                failed_sample = failed_details[:10]
                failed_snippet = "\n\n⚠️ <b>Sample Failed Groups:</b>\n" + "\n".join(failed_sample)
                if len(failed_details) > 10:
                    failed_snippet += f"\n<i>...and {len(failed_details) - 10} more. See detailed logs in /menu.</i>"

            summary_msg = (
                f"📊 <b>Broadcast Cycle #{self.current_cycle_id} Summary</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>Delivered Successfully:</b> {self.success_count} groups\n"
                f"❌ <b>Failed to Send:</b> {self.failed_count} groups\n"
                f"⏳ <b>Slowmode / Skipped:</b> {self.skipped_count} groups\n"
                f"⏱️ <b>Total Time Taken:</b> {mins}m {secs}s\n"
                f"🛡️ <b>Account Status:</b> Protected & Safe"
                f"{failed_snippet}"
            )
            await self.notify_admins(summary_msg)

            self.is_broadcasting = False
            self.is_paused = False

    def stop_broadcast(self):
        self.is_broadcasting = False
        self.is_paused = False

    def pause_broadcast(self):
        self.is_paused = True

    def resume_broadcast(self):
        self.is_paused = False

broadcaster = SafeBroadcaster()
