import re
import asyncio
import random
import logging
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
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
from database.crud import update_group_status
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

    async def join_single_group(self, identifier: str, group_db_id: int = None) -> dict:
        client = tg_manager.client
        if not client or not tg_manager.is_connected:
            return {"status": "error", "reason": "Userbot client is not connected."}

        parsed = extract_group_identifier(identifier)
        item_type = parsed["type"]
        val = parsed["value"]

        try:
            entity = None
            if item_type == "invite_hash":
                logger.info(f"Attempting to join private group with hash: {val}")
                try:
                    updates = await client(ImportChatInviteRequest(val))
                    if hasattr(updates, 'chats') and updates.chats:
                        entity = updates.chats[0]
                except UserAlreadyParticipantError:
                    return {"status": "ok", "reason": "Already participant", "joined": True}
                    
            elif item_type == "username":
                logger.info(f"Attempting to join public group @{val}")
                try:
                    updates = await client(JoinChannelRequest(val))
                    if hasattr(updates, 'chats') and updates.chats:
                        entity = updates.chats[0]
                except UserAlreadyParticipantError:
                    return {"status": "ok", "reason": "Already participant", "joined": True}
                    
            elif item_type == "chat_id":
                try:
                    entity = await client.get_entity(val)
                except Exception as e:
                    return {"status": "error", "reason": f"Could not find chat ID: {e}"}

            if group_db_id:
                async with AsyncSessionLocal() as session:
                    await update_group_status(session, group_db_id, "ACTIVE", is_success=True)

            return {"status": "ok", "reason": "Successfully joined", "joined": True}

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

    async def join_bulk_groups_safely(self, groups_list: list, progress_callback=None) -> dict:
        """
        Joins multiple groups safely with random delays between 45s to 90s to avoid account ban.
        """
        self.is_running = True
        total = len(groups_list)
        joined = 0
        failed = 0
        skipped = 0
        
        logger.info(f"Starting Safe Bulk Joiner for {total} groups with anti-ban delay...")

        for idx, grp in enumerate(groups_list, 1):
            if not self.is_running:
                logger.info("Bulk joiner cancelled by admin.")
                break

            grp_id = grp.id if hasattr(grp, 'id') else None
            identifier = grp.identifier if hasattr(grp, 'identifier') else str(grp)

            res = await self.join_single_group(identifier, grp_id)
            if res.get("status") == "ok":
                joined += 1
            elif res.get("status") == "flood_wait":
                wait_sec = res.get("seconds", 60)
                logger.info(f"Sleeping for {wait_sec}s due to Telegram FloodWait...")
                await asyncio.sleep(wait_sec + 5)
                # Retry once
                res2 = await self.join_single_group(identifier, grp_id)
                if res2.get("status") == "ok":
                    joined += 1
                else:
                    failed += 1
            else:
                failed += 1

            if progress_callback:
                try:
                    await progress_callback(idx, total, joined, failed, identifier)
                except Exception as e:
                    logger.warning(f"Joiner progress callback error: {e}")

            # Anti-ban sleep between joins
            if idx < total:
                delay = random.randint(config.MIN_JOIN_DELAY, config.MAX_JOIN_DELAY)
                logger.info(f"Anti-ban pause: sleeping {delay}s before next group join ({idx}/{total})...")
                await asyncio.sleep(delay)

        self.is_running = False
        return {"total": total, "joined": joined, "failed": failed, "skipped": skipped}

safe_joiner = SafeGroupJoiner()
