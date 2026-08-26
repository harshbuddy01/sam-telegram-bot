import logging
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User
import config
from database.database import AsyncSessionLocal
from database.crud import get_active_sender_account, add_or_update_sender_account, get_all_sender_accounts

logger = logging.getLogger(__name__)

class TelegramClientManager:
    _instance = None

    def __init__(self):
        self.client: TelegramClient | None = None
        self.is_connected = False
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

    def initialize_client(self, session_str: str = None) -> TelegramClient:
        sess = session_str or config.SESSION_STRING
        if sess:
            session_obj = StringSession(sess)
        else:
            session_obj = "promo_userbot_session"
            
        self.client = TelegramClient(
            session_obj,
            config.API_ID,
            config.API_HASH,
            device_model="Desktop",
            system_version="Linux/macOS",
            app_version="5.0.1"
        )
        return self.client

    async def ensure_connected(self) -> bool:
        """Ensures the active sender client is connected. Reconnects automatically if dropped."""
        if not self.client:
            return await self.start()
        try:
            if not self.client.is_connected():
                await self.client.connect()
            self.is_connected = await self.client.is_user_authorized()
            return self.is_connected
        except Exception as e:
            logger.warning(f"Reconnection needed: {e}. Reloading active sender from database...")
            return await self.start()

    async def start(self) -> bool:
        if not config.API_ID or not config.API_HASH:
            logger.warning("API_ID or API_HASH is not set! Userbot sender cannot start.")
            return False

        # Check if we have an active sender account in DB
        async with AsyncSessionLocal() as session:
            active_acc = await get_active_sender_account(session)
            if active_acc and active_acc.session_string:
                logger.info(f"Loading active sender account from DB: {active_acc.phone}")
                self.initialize_client(active_acc.session_string)
                self.active_account_id = active_acc.id
                self.active_phone = active_acc.phone
            else:
                self.initialize_client()

        try:
            await self.client.connect()
            self.is_connected = await self.client.is_user_authorized()
            if self.is_connected:
                me: User = await self.client.get_me()
                logger.info(f"Userbot connected successfully as @{me.username or me.first_name} (ID: {me.id}, Premium: {getattr(me, 'premium', False)})")
                return True
            else:
                logger.warning("Userbot client is NOT authorized yet. Please login via Bot menu or generate session string.")
                return False
        except Exception as e:
            logger.error(f"Error starting Userbot client: {e}")
            self.is_connected = False
            return False

    async def switch_to_account(self, session_string: str, account_id: int = None, phone: str = None) -> bool:
        """
        Disconnects current client and connects using another saved account session string.
        """
        try:
            if self.client and self.client.is_connected():
                await self.client.disconnect()

            self.initialize_client(session_string)
            await self.client.connect()
            self.is_connected = await self.client.is_user_authorized()
            if self.is_connected:
                self.active_account_id = account_id
                self.active_phone = phone
                me = await self.client.get_me()
                logger.info(f"Switched active sender account to @{me.username or me.first_name} ({phone})")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to switch account: {e}")
            return False

    async def get_me(self):
        if self.client and self.client.is_connected() and await self.client.is_user_authorized():
            return await self.client.get_me()
        return None

    async def export_session_string(self) -> str:
        if self.client and self.client.session:
            return StringSession.save(self.client.session)
        return ""

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
