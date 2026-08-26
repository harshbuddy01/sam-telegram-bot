import re
import asyncio
import random
import logging
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChannelsTooMuchError,
    FloodWaitError,
    ChannelPrivateError,
    ChatAdminRequiredError
)
from core.client import tg_manager
from database.database import AsyncSessionLocal
from database.crud import update_group_status, get_unjoined_groups
from sqlalchemy import update
from database.models import Group
import config

logger = logging.getLogger(__name__)

INVITE_HASH_REGEX = re.compile(r'(?:t\.me/joinchat/|t\.me/\+|telegram\.me/\+|telegram\.dog/\+)([a-zA-Z0-9_-]+)')
USERNAME_REGEX = re.compile(r'(?:t\.me/|telegram\.me/|@)([a-zA-Z0-9_]{4,32})')

def extract_group_identifier(raw_input: str) -> dict:
    raw = raw_input.strip()
    
    # Check for invite hash
    invite_match = INVITE_HASH_REGEX.search(raw)
    if invite_match:
        return {"type": "invite_hash", "value": invite_match.group(1), "raw": raw}
    
    # Check for username / t.me/username
    username_match = USERNAME_REGEX.search(raw)
    if username_match:
        return {"type": "username", "value": username_match.group(1), "raw": f"@{username_match.group(1)}"}
    
    # Check if raw chat ID
    if raw.startswith("-100") or (raw.startswith("-") and raw[1:].isdigit()):
        try:
            return {"type": "chat_id", "value": int(raw), "raw": raw}
        except ValueError:
            pass
            
    return {"type": "raw", "value": raw, "raw": raw}

class SafeGroupJoiner:
    def __init__(self):
        self.is_running = False
        self.should_stop = False
        self.bot_instance = None

    def set_bot_instance(self, bot):
        self.bot_instance = bot

    async def mark_group_joined(self, group_id: int):
        if not group_id:
            return
        async with AsyncSessionLocal() as session:
            await session.execute(update(Group).where(Group.id == group_id).values(is_joined=True, status="ACTIVE"))
            await session.commit()

    async def join_single_group(self, identifier: str, group_db_id: int = None) -> dict:
        client = tg_manager.client
        if not client or not tg_manager.is_connected:
            return {"status": "error", "reason": "Userbot client is not connected."}

        parsed = extract_group_identifier(identifier)
        item_type = parsed["type"]
        val = parsed["value"]

        try:
            if item_type == "invite_hash":
                logger.info(f"Joining private group with hash: {val}")
                try:
                    await client(ImportChatInviteRequest(val))
                except UserAlreadyParticipantError:
                    pass
                    
            elif item_type == "username":
                logger.info(f"Joining public group @{val}")
                try:
                    await client(JoinChannelRequest(val))
                except UserAlreadyParticipantError:
                    pass
                    
            elif item_type == "chat_id":
                try:
                    await client.get_entity(val)
                except Exception as e:
                    return {"status": "error", "reason": f"Could not find chat ID: {e}"}

            if group_db_id:
                await self.mark_group_joined(group_db_id)

            return {"status": "ok", "reason": "Successfully joined / Verified", "joined": True}

        except FloodWaitError as e:
            logger.warning(f"Telegram FloodWait triggered while joining: wait {e.seconds}s")
            return {"status": "flood_wait", "seconds": e.seconds, "reason": f"Telegram FloodWait: {e.seconds}s"}
            
        except (InviteHashExpiredError, InviteHashInvalidError):
            logger.warning(f"Invite link is invalid or expired: {identifier}")
            if group_db_id:
                async with AsyncSessionLocal() as session:
                    await update_group_status(session, group_db_id, "INVALID_LINK", error="Invite link expired or revoked")
            return {"status": "error", "reason": "Invite link expired or revoked"}
            
        except ChannelsTooMuchError:
            logger.error("Telegram limit reached: User account is in maximum number of channels/groups.")
            return {"status": "error", "reason": "Maximum channels/groups limit reached on Telegram account"}
            
        except ChannelPrivateError:
            if group_db_id:
                async with AsyncSessionLocal() as session:
                    await update_group_status(session, group_db_id, "BANNED", error="Channel is private or account is banned")
            return {"status": "error", "reason": "Channel is private or account is banned from this group"}
            
        except Exception as e:
            logger.error(f"Error joining group {identifier}: {e}")
            if group_db_id:
                async with AsyncSessionLocal() as session:
                    await update_group_status(session, group_db_id, "RESTRICTED", error=str(e))
            return {"status": "error", "reason": str(e)}

    async def resume_or_start_auto_join(self, progress_callback=None) -> dict:
        """
        Fetches all unjoined groups from DB and joins them safely with anti-ban delays.
        Resumes automatically where it was previously stopped.
        """
        if self.is_running:
            return {"status": "already_running"}

        async with AsyncSessionLocal() as session:
            unjoined_groups = await get_unjoined_groups(session)

        if not unjoined_groups:
            logger.info("All target groups are already joined and verified.")
            return {"total": 0, "joined": 0, "failed": 0, "status": "all_joined"}

        self.is_running = True
        self.should_stop = False
        total = len(unjoined_groups)
        joined = 0
        failed = 0

        logger.info(f"Resuming Safe Auto-Joiner for {total} unjoined groups...")

        for idx, grp in enumerate(unjoined_groups, 1):
            if self.should_stop or not self.is_running:
                logger.info("Auto-joiner paused/stopped by admin.")
                break

            res = await self.join_single_group(grp.identifier, grp.id)
            if res.get("status") == "ok":
                joined += 1
            elif res.get("status") == "flood_wait":
                wait_sec = res.get("seconds", 60)
                logger.info(f"FloodWait: sleeping {wait_sec}s...")
                await asyncio.sleep(wait_sec + 5)
                # Retry once
                res2 = await self.join_single_group(grp.identifier, grp.id)
                if res2.get("status") == "ok":
                    joined += 1
                else:
                    failed += 1
            else:
                failed += 1

            if progress_callback:
                try:
                    await progress_callback(idx, total, joined, failed, grp.identifier)
                except Exception:
                    pass

            # Anti-ban sleep between joins (random 45-90s)
            if idx < total and not self.should_stop:
                delay = random.randint(config.MIN_JOIN_DELAY, config.MAX_JOIN_DELAY)
                logger.info(f"Anti-ban pause: sleeping {delay}s before next group join ({idx}/{total})...")
                await asyncio.sleep(delay)

        self.is_running = False
        self.should_stop = False
        return {"total": total, "joined": joined, "failed": failed, "status": "completed"}

    def stop_joiner(self):
        self.should_stop = True
        self.is_running = False

safe_joiner = SafeGroupJoiner()
