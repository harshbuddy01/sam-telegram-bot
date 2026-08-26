"""
Terminal Session Generator Utility for Telethon StringSession.
Use this script if you want to quickly generate a session string for Railway without using the bot UI.
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    print("=" * 60)
    print("  TELEGRAM STRING SESSION GENERATOR (FOR TELETHON)")
    print("=" * 60)
    print("Get your API_ID and API_HASH from https://my.telegram.org\n")

    api_id_raw = input("Enter API_ID: ").strip()
    api_hash = input("Enter API_HASH: ").strip()

    if not api_id_raw.isdigit() or not api_hash:
        print("[ERROR] Invalid API ID or API Hash.")
        return

    api_id = int(api_id_raw)

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_str = client.session.save()
        me = await client.get_me()
        print("\n" + "=" * 60)
        print("🎉 SUCCESS! Authorized as:", me.first_name, f"(@{me.username or 'No username'})")
        print("=" * 60)
        print("\nHere is your SESSION_STRING (Copy this to Railway environment variables):\n")
        print(session_str)
        print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
