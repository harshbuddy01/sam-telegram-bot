import logging
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User
import config

logger = logging.getLogger(__name__)

class TelegramClientManager:
    _instance = None

    def __init__(self):
        self.client: TelegramClient | None = None
        self.is_connected = False
        self.phone = None
        self.phone_code_hash = None

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

    async def start(self) -> bool:
        if not config.API_ID or not config.API_HASH:
            logger.warning("API_ID or API_HASH is not set! Userbot sender cannot start.")
            return False

        if not self.client:
            self.initialize_client()

        try:
            await self.client.connect()
            self.is_connected = await self.client.is_user_authorized()
            if self.is_connected:
                me: User = await self.client.get_me()
                logger.info(f"Userbot connected successfully as @{me.username or me.first_name} (ID: {me.id}, Premium: {me.premium})")
                return True
            else:
                logger.warning("Userbot client is NOT authorized yet. Please login via Bot menu or generate session string.")
                return False
        except Exception as e:
            logger.error(f"Error starting Userbot client: {e}")
            self.is_connected = False
            return False

    async def get_me(self):
        if self.client and await self.client.is_user_authorized():
            return await self.client.get_me()
        return None

    async def export_session_string(self) -> str:
        if self.client and self.client.session:
            return StringSession.save(self.client.session)
        return ""

    # ================= Interactive Auth Helper Methods =================

    async def send_auth_code(self, phone_number: str) -> dict:
        if not self.client:
            self.initialize_client()
        if not self.client.is_connected():
            await self.client.connect()

        self.phone = phone_number.strip()
        try:
            sent_code = await self.client.send_code_request(self.phone)
            self.phone_code_hash = sent_code.phone_code_hash
            return {"status": "ok", "phone_code_hash": self.phone_code_hash}
        except Exception as e:
            logger.error(f"Failed to send code to {phone_number}: {e}")
            return {"status": "error", "message": str(e)}

    async def sign_in_with_code(self, code: str, password_2fa: str = None) -> dict:
        if not self.client or not self.phone or not self.phone_code_hash:
            return {"status": "error", "message": "No active sign in request. Please request OTP first."}
        
        try:
            await self.client.sign_in(
                phone=self.phone,
                code=code.strip(),
                phone_code_hash=self.phone_code_hash
            )
            self.is_connected = True
            session_str = await self.export_session_string()
            me = await self.client.get_me()
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
                        await self.client.sign_in(password=password_2fa.strip())
                        self.is_connected = True
                        session_str = await self.export_session_string()
                        me = await self.client.get_me()
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
