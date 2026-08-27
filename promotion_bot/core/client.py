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

                    # Auto-sync joined groups from Telegram API on boot
                    try:
                        dialog_groups = await self.fetch_joined_groups(acc.id)
                        if dialog_groups:
                            async with AsyncSessionLocal() as session:
                                res = await sync_telegram_groups(session, acc.id, dialog_groups)
                                logger.info(f"Auto-synced {res['total']} groups for {acc.phone} on startup ({res['added']} newly discovered)")
                    except Exception as eg:
                        logger.warning(f"Initial group sync warning for {acc.phone}: {eg}")
                else:
                    logger.warning(f"Session unauthorized for account #{acc.id} ({acc.phone}). Needs re-login.")
                    async with AsyncSessionLocal() as session:
                        await update_sender_account_status(session, acc.id, "NEED_LOGIN")
            except Exception as e:
                logger.error(f"Error loading client for account #{acc.id}: {e}")

        logger.info(f"Telegram connection pool ready: {len(self.clients)} active client(s).")

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

        Returns a list of dicts:
            [{chat_id, title, username, members_count, is_supergroup}, ...]
        Excludes private chats, broadcast-only channels, and bot conversations.
        """
        try:
            client = await self.get_client_for_account(account_id)
            if not client:
                logger.warning(f"fetch_joined_groups: no client for account #{account_id}")
                return []

            if not client.is_connected():
                await client.connect()

            dialogs = await client.get_dialogs(limit=None)
            groups: list[dict] = []

            for dialog in dialogs:
                if dialog.is_user:
                    continue

                entity = dialog.entity

                if dialog.is_group:
                    is_supergroup = isinstance(entity, Channel)
                    members = getattr(entity, "participants_count", 0) or 0
                    username = getattr(entity, "username", None)
                    title = dialog.name or getattr(entity, "title", "") or "Untitled Group"

                    groups.append({
                        "chat_id": entity.id,
                        "title": title,
                        "username": username,
                        "members_count": members,
                        "is_supergroup": is_supergroup,
                    })

                elif isinstance(entity, Channel):
                    if not entity.broadcast or getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False):
                        groups.append({
                            "chat_id": entity.id,
                            "title": getattr(entity, "title", "") or dialog.name or "Untitled Group",
                            "username": getattr(entity, "username", None),
                            "members_count": getattr(entity, "participants_count", 0) or 0,
                            "is_supergroup": True,
                        })

                elif isinstance(entity, Chat):
                    if not getattr(entity, "deactivated", False) and not getattr(entity, "left", False):
                        groups.append({
                            "chat_id": entity.id,
                            "title": getattr(entity, "title", "") or dialog.name or "Untitled Group",
                            "username": None,
                            "members_count": getattr(entity, "participants_count", 0) or 0,
                            "is_supergroup": False,
                        })

            # Deduplicate by chat_id
            seen_ids = set()
            unique_groups = []
            for g in groups:
                if g["chat_id"] not in seen_ids:
                    seen_ids.add(g["chat_id"])
                    unique_groups.append(g)

            logger.info(
                f"fetch_joined_groups: account #{account_id} — found {len(unique_groups)} group(s) "
                f"out of {len(dialogs)} total dialog(s)"
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
