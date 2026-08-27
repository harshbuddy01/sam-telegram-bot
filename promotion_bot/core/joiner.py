import asyncio
import re
import random
import logging
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UserAlreadyParticipantError,
    InviteHashExpiredError, PeerFloodError, UserBannedInChannelError
)
from core.client import tg_manager
from database.database import AsyncSessionLocal
from database.crud import (
    get_unjoined_groups_for_account,
    update_group_status,
    check_daily_join_limit,
    increment_daily_joins,
    log_join_attempt
)
import config

logger = logging.getLogger(__name__)


def extract_group_identifier(raw_input: str) -> dict:
    raw = raw_input.strip()
    invite_match = re.match(r'https?://t\.me/(joinchat/|\+)([a-zA-Z0-9_\-]+)', raw)
    if invite_match:
        return {"type": "invite_hash", "value": invite_match.group(2)}
    username_match = re.match(r'https?://t\.me/([a-zA-Z][a-zA-Z0-9_]{3,31})$', raw)
    if username_match:
        return {"type": "username", "value": username_match.group(1)}
    if raw.startswith("@"):
        return {"type": "username", "value": raw.lstrip("@")}
    if raw.startswith("-100") and raw.lstrip("-").isdigit():
        return {"type": "chat_id", "value": int(raw)}
    return {"type": "raw", "value": raw}


class SafeGroupJoiner:
    def __init__(self):
        self.is_running = False
        self.should_stop = False
        self._lock = asyncio.Lock()
        self.bot_instance = None

    def set_bot_instance(self, bot):
        self.bot_instance = bot

    async def join_single_group(self, identifier: str, account_id: int, group_db_id: int = None) -> dict:
        client = await tg_manager.get_client_for_account(account_id)
        if not client:
            return {"status": "error", "reason": "Client not connected for this account"}

        parsed = extract_group_identifier(identifier)

        try:
            if parsed["type"] == "invite_hash":
                try:
                    res = await client(ImportChatInviteRequest(parsed["value"]))
                    if group_db_id:
                        async with AsyncSessionLocal() as session:
                            await update_group_status(session, group_db_id, "ACTIVE", is_success=True)
                    return {"status": "ok", "reason": "Joined via invite link"}
                except UserAlreadyParticipantError:
                    if group_db_id:
                        async with AsyncSessionLocal() as session:
                            await update_group_status(session, group_db_id, "ACTIVE", is_success=True)
                    return {"status": "already_member", "reason": "Already a member"}
                except InviteHashExpiredError:
                    if group_db_id:
                        async with AsyncSessionLocal() as session:
                            await update_group_status(session, group_db_id, "INVALID_LINK", error="Invite link expired")
                    return {"status": "error", "reason": "Invite link expired or invalid"}

            elif parsed["type"] == "username":
                try:
                    entity = await client.get_entity(parsed["value"])
                    await client(JoinChannelRequest(entity))
                    if group_db_id:
                        async with AsyncSessionLocal() as session:
                            await update_group_status(session, group_db_id, "ACTIVE", is_success=True)
                    return {"status": "ok", "reason": "Joined via username"}
                except UserAlreadyParticipantError:
                    if group_db_id:
                        async with AsyncSessionLocal() as session:
                            await update_group_status(session, group_db_id, "ACTIVE", is_success=True)
                    return {"status": "already_member", "reason": "Already a member"}

            elif parsed["type"] == "chat_id":
                entity = await client.get_entity(parsed["value"])
                await client(JoinChannelRequest(entity))
                if group_db_id:
                    async with AsyncSessionLocal() as session:
                        await update_group_status(session, group_db_id, "ACTIVE", is_success=True)
                return {"status": "ok", "reason": "Joined via chat ID"}

            else:
                try:
                    entity = await client.get_entity(parsed["value"])
                    await client(JoinChannelRequest(entity))
                    if group_db_id:
                        async with AsyncSessionLocal() as session:
                            await update_group_status(session, group_db_id, "ACTIVE", is_success=True)
                    return {"status": "ok", "reason": "Joined"}
                except Exception as e:
                    if group_db_id:
                        async with AsyncSessionLocal() as session:
                            await update_group_status(session, group_db_id, "RESTRICTED", error=str(e))
                    return {"status": "error", "reason": str(e)}

        except FloodWaitError as e:
            return {"status": "flood_wait", "reason": f"FloodWait: {e.seconds}s", "seconds": e.seconds}

        except PeerFloodError:
            return {"status": "peer_flood", "reason": "Telegram PeerFlood triggered"}

        except ChannelPrivateError:
            if group_db_id:
                async with AsyncSessionLocal() as session:
                    await update_group_status(session, group_db_id, "BANNED", error="Channel is private or banned")
            return {"status": "error", "reason": "Channel is private or account is banned"}

        except UserBannedInChannelError:
            if group_db_id:
                async with AsyncSessionLocal() as session:
                    await update_group_status(session, group_db_id, "BANNED", error="Account banned in this group")
            return {"status": "error", "reason": "Account is banned in this group"}

        except Exception as e:
            logger.error(f"Error joining {identifier}: {e}")
            if group_db_id:
                async with AsyncSessionLocal() as session:
                    await update_group_status(session, group_db_id, "RESTRICTED", error=str(e))
            return {"status": "error", "reason": str(e)}

    async def auto_join_for_account(self, account_id: int, progress_callback=None) -> dict:
        if self._lock.locked() or self.is_running:
            return {"status": "already_running"}

        async with self._lock:
            async with AsyncSessionLocal() as session:
                unjoined = await get_unjoined_groups_for_account(session, account_id)

            if not unjoined:
                return {"total": 0, "joined": 0, "failed": 0, "already_member": 0, "status": "all_joined"}

            self.is_running = True
            self.should_stop = False
            total = len(unjoined)
            joined = 0
            failed = 0
            already_member = 0
            session_joins = 0  # Track joins in this session for session limit

            logger.info(f"Starting auto-join for account #{account_id}: {total} groups")

            for idx, grp in enumerate(unjoined, 1):
                if self.should_stop or not self.is_running:
                    logger.info("Auto-joiner stopped by admin.")
                    break

                # Check daily limit
                async with AsyncSessionLocal() as session:
                    limit_info = await check_daily_join_limit(session, account_id)
                if not limit_info["allowed"]:
                    logger.info(f"Daily join limit reached ({limit_info['used']}/{limit_info['limit']}). Stopping.")
                    break

                # Check session limit
                if session_joins >= config.MAX_JOINS_PER_SESSION:
                    logger.info(f"Session limit ({config.MAX_JOINS_PER_SESSION}) reached. Pausing {config.SESSION_JOIN_COOLDOWN}s...")
                    if progress_callback:
                        try:
                            await progress_callback(idx, total, joined, failed, f"⏳ Session limit reached. Pausing {config.SESSION_JOIN_COOLDOWN // 60}min...")
                        except Exception:
                            pass
                    await asyncio.sleep(config.SESSION_JOIN_COOLDOWN)
                    session_joins = 0

                res = await self.join_single_group(grp.identifier, account_id, grp.id)
                status = res.get("status")

                async with AsyncSessionLocal() as session:
                    if status == "ok":
                        joined += 1
                        session_joins += 1
                        await increment_daily_joins(session, account_id)
                        await log_join_attempt(session, account_id, grp.identifier, "JOINED")
                        grp.is_joined = True
                        logger.info(f"✅ Joined ({joined}/{total}): {grp.identifier}")
                    elif status == "already_member":
                        already_member += 1
                        await log_join_attempt(session, account_id, grp.identifier, "ALREADY_MEMBER")
                        grp.is_joined = True
                    elif status == "flood_wait":
                        wait_sec = res.get("seconds", 60)
                        await log_join_attempt(session, account_id, grp.identifier, "FLOOD_WAIT", f"Wait {wait_sec}s")
                        logger.info(f"FloodWait: sleeping {wait_sec}s...")
                        await asyncio.sleep(wait_sec + 10)
                        # Retry once
                        res2 = await self.join_single_group(grp.identifier, account_id, grp.id)
                        if res2.get("status") == "ok":
                            joined += 1
                            session_joins += 1
                            await increment_daily_joins(session, account_id)
                            await log_join_attempt(session, account_id, grp.identifier, "JOINED")
                        else:
                            failed += 1
                            await log_join_attempt(session, account_id, grp.identifier, "FAILED", res2.get("reason"))
                    elif status == "peer_flood":
                        await log_join_attempt(session, account_id, grp.identifier, "FAILED", "PeerFlood")
                        logger.info("PeerFlood detected. Stopping joiner for safety.")
                        break
                    else:
                        failed += 1
                        await log_join_attempt(session, account_id, grp.identifier, "FAILED", res.get("reason"))
                        logger.info(f"❌ Failed ({idx}/{total}): {grp.identifier} — {res.get('reason')}")

                if progress_callback:
                    try:
                        await progress_callback(idx, total, joined, failed, grp.identifier)
                    except Exception:
                        pass

                # Anti-ban delay
                if idx < total and not self.should_stop:
                    if status in ("ok", "already_member"):
                        delay = random.randint(config.MIN_JOIN_DELAY, config.MAX_JOIN_DELAY)
                        logger.info(f"⏳ Anti-ban cooldown: {delay}s")
                    else:
                        delay = 2
                    await asyncio.sleep(delay)

            self.is_running = False
            self.should_stop = False
            return {"total": total, "joined": joined, "failed": failed, "already_member": already_member, "status": "completed"}

    def stop_joiner(self):
        self.should_stop = True
        self.is_running = False


safe_joiner = SafeGroupJoiner()
