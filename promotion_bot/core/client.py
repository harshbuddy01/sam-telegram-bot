import logging
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat
import config
from database.database import AsyncSessionLocal
from database.crud import get_active_sender_account, add_or_update_sender_account, get_all_sender_accounts

logger = logging.getLogger(__name__)

class TelegramClientManager:
    _instance = None

    def __init__(self):
        # Pool of active clients: account_id -> TelegramClient
        self.clients: dict[int, TelegramClient] = {}
        self.active_account_id = None
        self.active_phone = None
        # Isolated client for adding new accounts
        self.temp_auth_client: TelegramClient | None = None
        self.auth_phone = None
        self.auth_code_hash = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TelegramClientManager()
        return cls._instance

    @property
    def client(self) -> TelegramClient | None:
        """Returns active sender client, or the first available client in the pool."""
        if self.active_account_id and self.active_account_id in self.clients:
            return self.clients[self.active_account_id]
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
            system_version="Linux/macOS",
            app_version="5.0.1"
        )

    async def get_client_for_account(self, account_id: int) -> TelegramClient | None:
        """Retrieves or connects a dedicated client instance for a given account_id."""
        if account_id in self.clients:
            c = self.clients[account_id]
            if not c.is_connected():
                try:
                    await c.connect()
                except Exception as e:
                    logger.warning(f"Error reconnecting client for account #{account_id}: {e}")
            return c

        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)
            acc = next((a for a in accounts if a.id == account_id), None)
            if not acc or not acc.session_string:
                return None

        c = self.create_client_instance(acc.session_string)
        try:
            await c.connect()
            if await c.is_user_authorized():
                self.clients[account_id] = c
                return c
        except Exception as e:
            logger.error(f"Failed to connect client for {acc.phone}: {e}")
        return None

    async def ensure_connected(self) -> bool:
        """Ensures the primary active sender client is connected."""
        c = self.client
        if not c:
            return await self.start()
        try:
            if not c.is_connected():
                await c.connect()
            return await c.is_user_authorized()
        except Exception as e:
            logger.warning(f"Primary reconnection needed: {e}. Reinitializing...")
            return await self.start()

    async def start(self) -> bool:
        if not config.API_ID or not config.API_HASH:
            logger.warning("API_ID or API_HASH is not set! Userbot sender cannot start.")
            return False

        async with AsyncSessionLocal() as session:
            accounts = await get_all_sender_accounts(session)
            active_acc = await get_active_sender_account(session)

        if not accounts:
            logger.info("No sender accounts saved in database yet.")
            return False

        connected_any = False
        for acc in accounts:
            if acc.session_string:
                try:
                    c = self.create_client_instance(acc.session_string)
                    await c.connect()
                    if await c.is_user_authorized():
                        self.clients[acc.id] = c
                        connected_any = True
                        me: User = await c.get_me()
                        logger.info(f"Loaded client for {acc.phone} (@{me.username or me.first_name}, ID: {me.id})")
                except Exception as e:
                    logger.warning(f"Could not connect {acc.phone}: {e}")

        if active_acc and active_acc.id in self.clients:
            self.active_account_id = active_acc.id
            self.active_phone = active_acc.phone
        elif self.clients:
            self.active_account_id = next(iter(self.clients.keys()))

        return connected_any

    async def switch_to_account(self, session_string: str, account_id: int = None, phone: str = None) -> bool:
        """Connects or switches the primary active sender account."""
        try:
            c = await self.get_client_for_account(account_id)
            if c and await c.is_user_authorized():
                self.active_account_id = account_id
                self.active_phone = phone
                me = await c.get_me()
                logger.info(f"Switched primary active sender to @{me.username or me.first_name} ({phone})")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to switch account: {e}")
            return False

    async def get_me(self, account_id: int = None):
        c = (await self.get_client_for_account(account_id)) if account_id else self.client
        if c and c.is_connected() and await c.is_user_authorized():
            return await c.get_me()
        return None

    async def export_session_string(self, account_id: int = None) -> str:
        c = (await self.get_client_for_account(account_id)) if account_id else self.client
        if c and c.session:
            return StringSession.save(c.session)
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

            dialogs = await client.get_dialogs()
            groups: list[dict] = []

            for dialog in dialogs:
                entity = dialog.entity

                # --- small group chats (telethon.tl.types.Chat) ---
                if isinstance(entity, Chat):
                    # Skip deactivated / kicked chats
                    if getattr(entity, "deactivated", False) or getattr(entity, "left", False):
                        continue
                    groups.append({
                        "chat_id": entity.id,
                        "title": entity.title or "",
                        "username": None,
                        "members_count": getattr(entity, "participants_count", 0) or 0,
                        "is_supergroup": False,
                    })

                # --- supergroups & channels (telethon.tl.types.Channel) ---
                elif isinstance(entity, Channel):
                    # Skip broadcast-only channels (no megagroup flag)
                    if entity.broadcast and not entity.megagroup:
                        continue
                    # Only keep megagroups / gigagroups (supergroups)
                    if not entity.megagroup and not getattr(entity, "gigagroup", False):
                        continue
                    groups.append({
                        "chat_id": entity.id,
                        "title": entity.title or "",
                        "username": entity.username,
                        "members_count": getattr(entity, "participants_count", 0) or 0,
                        "is_supergroup": True,
                    })

            logger.info(
                f"fetch_joined_groups: account #{account_id} — found {len(groups)} group(s) "
                f"out of {len(dialogs)} total dialog(s)"
            )
            return groups

        except Exception as e:
            logger.error(f"fetch_joined_groups failed for account #{account_id}: {e}", exc_info=True)
            return []

    # ================= Interactive Auth Helper Methods (Isolated) =================

    async def send_auth_code(self, phone_number: str) -> dict:
        self.auth_phone = phone_number.strip()
        try:
            # Create a separate, isolated client specifically for this login session
            if self.temp_auth_client and self.temp_auth_client.is_connected():
                await self.temp_auth_client.disconnect()

            self.temp_auth_client = TelegramClient(
                StringSession(""),
                config.API_ID,
                config.API_HASH,
                device_model="Desktop",
                system_version="Linux/macOS",
                app_version="5.0.1"
            )
            await self.temp_auth_client.connect()

            sent_code = await self.temp_auth_client.send_code_request(self.auth_phone)
            self.auth_code_hash = sent_code.phone_code_hash
            return {"status": "ok", "phone_code_hash": self.auth_code_hash}
        except Exception as e:
            logger.error(f"Failed to send code to {phone_number}: {e}")
            return {"status": "error", "message": str(e)}

    async def sign_in_with_code(self, code: str, password_2fa: str = None) -> dict:
        auth_client = self.temp_auth_client or self.client
        if not auth_client or not self.auth_phone or not self.auth_code_hash:
            return {"status": "error", "message": "No active sign in request. Please request OTP first."}
        
        try:
            if not auth_client.is_connected():
                await auth_client.connect()

            if code:
                await auth_client.sign_in(
                    phone=self.auth_phone,
                    code=code.strip(),
                    phone_code_hash=self.auth_code_hash
                )
            elif password_2fa:
                await auth_client.sign_in(password=password_2fa.strip())

            session_str = StringSession.save(auth_client.session)
            me = await auth_client.get_me()
            
            # Save new account into SQLite
            async with AsyncSessionLocal() as session:
                acc = await add_or_update_sender_account(
                    session=session,
                    phone=self.auth_phone,
                    session_string=session_str,
                    user_id=me.id,
                    username=me.username,
                    first_name=me.first_name,
                    is_premium=getattr(me, 'premium', False) or False,
                    set_active=True
                )

            # Switch the main client to this newly added account
            await self.switch_to_account(session_str, acc.id, acc.phone)

            # Disconnect the temporary auth client cleanly
            if self.temp_auth_client and self.temp_auth_client != self.client:
                try:
                    await self.temp_auth_client.disconnect()
                except Exception:
                    pass
                self.temp_auth_client = None

            return {
                "status": "ok",
                "session_string": session_str,
                "user": f"@{me.username or me.first_name} (ID: {me.id})"
            }
        except Exception as e:
            from telethon.errors import SessionPasswordNeededError
            if isinstance(e, SessionPasswordNeededError):
                if password_2fa:
                    try:
                        await auth_client.sign_in(password=password_2fa.strip())
                        session_str = StringSession.save(auth_client.session)
                        me = await auth_client.get_me()
                        
                        async with AsyncSessionLocal() as session:
                            acc = await add_or_update_sender_account(
                                session=session,
                                phone=self.auth_phone,
                                session_string=session_str,
                                user_id=me.id,
                                username=me.username,
                                first_name=me.first_name,
                                is_premium=getattr(me, 'premium', False) or False,
                                set_active=True
                            )

                        await self.switch_to_account(session_str, acc.id, acc.phone)
                        return {
                            "status": "ok",
                            "session_string": session_str,
                            "user": f"@{me.username or me.first_name} (ID: {me.id})"
                        }
                    except Exception as e2:
                        return {"status": "error", "message": f"2FA Password failed: {e2}"}
                else:
                    return {"status": "2fa_required", "message": "Two-step verification (2FA) password required."}
            logger.error(f"Sign-in failed: {e}")
            return {"status": "error", "message": str(e)}

tg_manager = TelegramClientManager.get_instance()
