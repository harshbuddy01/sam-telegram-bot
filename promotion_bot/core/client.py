import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError
)
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    get_active_sender_account,
    add_or_update_sender_account,
    update_sender_account_status,
    sync_telegram_groups
)
import config

logger = logging.getLogger(__name__)


class TelegramClientManager:
    _instance = None

    def __init__(self):
        self.clients: dict[int, TelegramClient] = {}
        self.primary_client: TelegramClient | None = None
        self.temp_auth_client: TelegramClient | None = None
        self.phone_code_hash: str | None = None
        self.temp_phone: str | None = None
        self.bot_instance = None

    def set_bot_instance(self, bot):
        self.bot_instance = bot

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TelegramClientManager()
        return cls._instance

    @property
    def client(self) -> TelegramClient | None:
        if self.primary_client:
            return self.primary_client
        if self.clients:
            return next(iter(self.clients.values()))
        return None

    @property
    def is_connected(self) -> bool:
        c = self.client
        return c is not None and c.is_connected()

    def create_client_instance(self, session_str: str) -> TelegramClient:
        return TelegramClient(
            StringSession(session_str),
            config.API_ID,
            config.API_HASH,
            device_model="Desktop",
            system_version="Linux",
            app_version="4.16.8",
            lang_code="en",
            system_lang_code="en"
        )

    async def get_client_for_account(self, account_id: int) -> TelegramClient | None:
        if account_id in self.clients:
            c = self.clients[account_id]
            if not c.is_connected():
                try:
                    await c.connect()
                except Exception as e:
                    logger.warning(f"Could not reconnect client for #{account_id}: {e}")
            return c

        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)
            acc = next((a for a in accounts if a.id == account_id), None)
            if acc and acc.session_string:
                client = self.create_client_instance(acc.session_string)
                try:
                    await client.connect()
                    if await client.is_user_authorized():
                        self.clients[acc.id] = client
                        return client
                except Exception as e:
                    logger.error(f"Failed to connect client for #{acc.id} ({acc.phone}): {e}")
        return None

    async def ensure_connected(self) -> bool:
        if not self.primary_client:
            return False
        if not self.primary_client.is_connected():
            try:
                await self.primary_client.connect()
            except Exception as e:
                logger.error(f"Reconnect failed: {e}")
                return False
        return await self.primary_client.is_user_authorized()

    async def start(self):
        logger.info("Initializing multi-account Telegram connection pool...")
        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)

        if not accounts and config.SESSION_STRING:
            logger.info("Importing SESSION_STRING from environment variable...")
            try:
                temp_c = self.create_client_instance(config.SESSION_STRING)
                await temp_c.connect()
                if await temp_c.is_user_authorized():
                    me = await temp_c.get_me()
                    async with AsyncSessionLocal() as session:
                        await add_or_update_sender_account(
                            session=session,
                            phone=me.phone or "Unknown",
                            session_string=config.SESSION_STRING,
                            user_id=me.id,
                            username=me.username,
                            first_name=me.first_name,
                            is_premium=getattr(me, "premium", False),
                            set_active=True
                        )
                        accounts = await get_all_sender_accounts(session)
                await temp_c.disconnect()
            except Exception as e:
                logger.error(f"Failed to import SESSION_STRING: {e}")

        for acc in accounts:
            if not acc.session_string:
                continue
            try:
                client = self.create_client_instance(acc.session_string)
                await client.connect()
                if await client.is_user_authorized():
                    self.clients[acc.id] = client
                    me = await client.get_me()
                    logger.info(f"Loaded client for {acc.phone} (@{me.username or me.first_name}, ID: {me.id})")
                    if acc.is_active or self.primary_client is None:
                        self.primary_client = client
                else:
                    logger.warning(f"Session unauthorized for account #{acc.id} ({acc.phone}). Needs re-login.")
                    async with AsyncSessionLocal() as session:
                        await update_sender_account_status(session, acc.id, "NEED_LOGIN")
            except Exception as e:
                logger.error(f"Error loading client for account #{acc.id}: {e}")

        logger.info(f"Telegram connection pool ready: {len(self.clients)} active client(s).")
        # Run background sync so startup is instant and healthcheck passes immediately
        asyncio.create_task(self._startup_sync_task())

    async def _startup_sync_task(self):
        """Runs in background on startup to sync all account groups without blocking boot."""
        # Wait longer so bot_instance is properly set and Railway healthcheck passes
        await asyncio.sleep(5)
        logger.info("Starting background auto-sync for all connected accounts...")
        results = await self.sync_all_accounts()

        # Log results clearly in Railway logs for debugging
        for acc_id, res in results.items():
            phone = res.get("phone", f"#{acc_id}")
            status = res.get("status", "unknown")
            total = res.get("total", 0)
            added = res.get("added", 0)
            error = res.get("error", "")
            if status == "ok":
                logger.info(f"AUTO-SYNC ✅ {phone}: {total} groups in DB ({added} new)")
            else:
                logger.warning(f"AUTO-SYNC ⚠️ {phone}: status={status} error={error}")

        logger.info("Background auto-sync task completed.")

        # Notify admin if bot_instance is ready
        if self.bot_instance and config.ADMIN_IDS:
            msg_lines = ["🔄 <b>Telegram Groups Auto-Sync Done</b>", "━━━━━━━━━━━━━━━━━━━━"]
            for acc_id, res in results.items():
                status_icon = "✅" if res.get("status") == "ok" else "⚠️"
                msg_lines.append(
                    f"{status_icon} <b>{res.get('phone', f'Account #{acc_id}')}</b>: "
                    f"<code>{res.get('total', 0)} groups</code> "
                    f"(+{res.get('added', 0)} new)"
                )
            msg_lines.append("\n👉 <i>Type /menu to see updated group counts.</i>")
            msg_text = "\n".join(msg_lines)
            for admin_id in config.ADMIN_IDS:
                try:
                    await self.bot_instance.send_message(admin_id, msg_text, parse_mode="HTML")
                except Exception:
                    pass

    async def sync_all_accounts(self) -> dict:
        """Syncs Telegram API groups for all loaded accounts. Returns summary dict."""
        results = {}
        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)

        for acc in accounts:
            if acc.id not in self.clients:
                results[acc.id] = {"phone": acc.phone, "status": "not_connected", "total": 0, "added": 0}
                continue
            try:
                groups = await self.fetch_joined_groups(acc.id)
                async with AsyncSessionLocal() as session:
                    res = await sync_telegram_groups(session, acc.id, groups)
                    results[acc.id] = {
                        "phone": acc.phone,
                        "status": "ok",
                        "total": res["total"],
                        "added": res["added"],
                        "existing": res["existing"]
                    }
                    logger.info(f"Sync complete for {acc.phone}: {res['total']} total groups ({res['added']} newly added)")
            except Exception as e:
                logger.error(f"Sync error for {acc.phone}: {e}")
                results[acc.id] = {"phone": acc.phone, "status": "error", "error": str(e), "total": 0, "added": 0}

        return results

    async def switch_to_account(self, session_string: str, account_id: int = None, phone: str = None) -> bool:
        if account_id and account_id in self.clients:
            self.primary_client = self.clients[account_id]
            logger.info(f"Switched active client in memory to account #{account_id}")
            return True

        client = self.create_client_instance(session_string)
        try:
            await client.connect()
            if await client.is_user_authorized():
                self.primary_client = client
                if account_id:
                    self.clients[account_id] = client
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to switch account: {e}")
            return False

    async def get_me(self, account_id: int = None) -> User | None:
        client = await self.get_client_for_account(account_id) if account_id else self.client
        if client and client.is_connected():
            return await client.get_me()
        return None

    async def export_session_string(self, account_id: int = None) -> str:
        client = await self.get_client_for_account(account_id) if account_id else self.client
        if client and isinstance(client.session, StringSession):
            return client.session.save()
        return ""

    # ================= Fetch Joined Groups =================

    async def fetch_joined_groups(self, account_id: int) -> list[dict]:
        """Fetch all groups and supergroups the account has joined.
        Checks both main folder (0) and archived folder (1) to find all joined groups.
        Excludes private chats, bots, and broadcast-only channels.
        """
        try:
            client = await self.get_client_for_account(account_id)
            if not client:
                logger.warning(f"fetch_joined_groups: no client for account #{account_id}")
                return []

            if not client.is_connected():
                await client.connect()

            dialogs = []
            # 1. Fetch main dialogs (folder 0)
            try:
                main_dialogs = await client.get_dialogs(limit=None, folder=0)
                dialogs.extend(main_dialogs)
            except Exception as e:
                logger.warning(f"get_dialogs(folder=0) fallback for #{account_id}: {e}")
                main_dialogs = await client.get_dialogs(limit=None)
                dialogs.extend(main_dialogs)

            # 2. Fetch archived dialogs (folder 1) — where users frequently keep large group lists
            try:
                archived_dialogs = await client.get_dialogs(limit=None, folder=1)
                if archived_dialogs:
                    dialogs.extend(archived_dialogs)
                    logger.info(f"Account #{account_id}: found {len(archived_dialogs)} archived dialog(s)")
            except Exception as e:
                logger.debug(f"No archived folder or note for #{account_id}: {e}")

            groups: list[dict] = []

            for dialog in dialogs:
                if dialog.is_user:
                    continue

                entity = dialog.entity

                # Skip if already left or deactivated
                if getattr(entity, "left", False) or getattr(entity, "deactivated", False):
                    continue

                is_group = False
                is_supergroup = False

                if isinstance(entity, Channel):
                    is_megagroup = getattr(entity, "megagroup", False)
                    is_gigagroup = getattr(entity, "gigagroup", False)
                    is_broadcast = getattr(entity, "broadcast", False)

                    # Pure broadcast channels: skip (cannot post promo messages there)
                    if is_broadcast and not is_megagroup and not is_gigagroup:
                        continue

                    # Supergroup / Discussion group / Megagroup
                    is_group = True
                    is_supergroup = True

                elif isinstance(entity, Chat):
                    # Basic Group
                    is_group = True
                    is_supergroup = False

                elif dialog.is_group:
                    is_group = True

                if is_group:
                    members = getattr(entity, "participants_count", 0) or 0
                    username = getattr(entity, "username", None)
                    title = dialog.name or getattr(entity, "title", "") or f"Group {entity.id}"

                    groups.append({
                        "chat_id": entity.id,
                        "title": title,
                        "username": username,
                        "members_count": members,
                        "is_supergroup": is_supergroup,
                    })

            # Deduplicate by chat_id
            seen_ids: set[int] = set()
            unique_groups: list[dict] = []
            for g in groups:
                if g["chat_id"] not in seen_ids:
                    seen_ids.add(g["chat_id"])
                    unique_groups.append(g)

            logger.info(
                f"fetch_joined_groups: account #{account_id} — "
                f"found {len(unique_groups)} group(s) across {len(dialogs)} dialog(s)"
            )
            return unique_groups

        except Exception as e:
            logger.error(f"fetch_joined_groups failed for account #{account_id}: {e}", exc_info=True)
            return []

    # ================= Interactive Auth Helper Methods (Isolated) =================

    async def send_auth_code(self, phone_number: str) -> dict:
        clean_phone = phone_number.strip().replace(" ", "").replace("-", "")
        self.temp_phone = clean_phone
        try:
            if self.temp_auth_client and self.temp_auth_client.is_connected():
                await self.temp_auth_client.disconnect()

            self.temp_auth_client = TelegramClient(
                StringSession(),
                config.API_ID,
                config.API_HASH,
                device_model="Desktop",
                system_version="Linux",
                app_version="4.16.8",
                lang_code="en",
                system_lang_code="en"
            )
            await self.temp_auth_client.connect()
            sent_code = await self.temp_auth_client.send_code_request(clean_phone)
            self.phone_code_hash = sent_code.phone_code_hash
            return {"status": "ok", "message": "Code sent successfully"}
        except Exception as e:
            logger.error(f"send_auth_code failed for {clean_phone}: {e}")
            return {"status": "error", "message": str(e)}

    async def sign_in_with_code(self, code: str, password_2fa: str = None) -> dict:
        if not self.temp_auth_client or not self.temp_auth_client.is_connected():
            return {"status": "error", "message": "Auth session expired. Please start over."}

        clean_code = code.strip().replace(" ", "").replace("-", "")

        try:
            if password_2fa:
                user = await self.temp_auth_client.sign_in(password=password_2fa.strip())
            else:
                user = await self.temp_auth_client.sign_in(
                    phone=self.temp_phone,
                    code=clean_code,
                    phone_code_hash=self.phone_code_hash
                )

            session_str = self.temp_auth_client.session.save()
            async with AsyncSessionLocal() as session:
                account = await add_or_update_sender_account(
                    session=session,
                    phone=self.temp_phone,
                    session_string=session_str,
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    is_premium=getattr(user, "premium", False),
                    set_active=True
                )

            self.clients[account.id] = self.temp_auth_client
            self.primary_client = self.temp_auth_client
            self.temp_auth_client = None

            # Sync groups immediately after successful login
            try:
                dialog_groups = await self.fetch_joined_groups(account.id)
                if dialog_groups:
                    async with AsyncSessionLocal() as session:
                        await sync_telegram_groups(session, account.id, dialog_groups)
            except Exception:
                pass

            return {
                "status": "ok",
                "message": "Login successful",
                "session_string": session_str,
                "user": f"@{user.username}" if user.username else user.first_name,
                "account_id": account.id
            }

        except SessionPasswordNeededError:
            return {"status": "2fa_required", "message": "2FA Cloud Password required"}
        except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
            return {"status": "error", "message": f"Invalid or expired OTP code: {e}"}
        except PasswordHashInvalidError:
            return {"status": "error", "message": "Incorrect 2FA password"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


tg_manager = TelegramClientManager.get_instance()
