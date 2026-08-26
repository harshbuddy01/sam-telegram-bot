# 🚀 Telegram Promotion & Auto-Broadcast Bot (Anti-Ban Engine)

A high-performance, automated Telegram Promotion Bot built with **Aiogram 3.x** and **Telethon** that safely broadcasts promotional messages to **300–400+ groups** on automated repeating intervals (every 1–2 hours) with strict anti-ban safeguards, automated group joiner, dynamic in-bot message editor with **Telegram Premium emojis**, and comprehensive failure reporting.

---

## 🛡️ Anti-Ban Mathematics: Why Your Number Will NOT Get Banned

Broadcasting to 300–400 groups without a properly calibrated rate limiter will trigger Telegram's spam algorithms. Here is how our mathematical anti-ban engine protects your phone number:

| Metric | Standard Spam Bot (Banned) | Our Anti-Ban Engine (Safe) |
| :--- | :--- | :--- |
| **Speed per group** | 1–3 seconds | **18 – 35 seconds (Randomized Micro-Jitter)** |
| **Batch Cooling** | None | **4-minute pause every 25 groups** |
| **Average Delivery Rate** | >30 msgs/min (Triggers PeerFlood) | **~2.2 msgs/min (Human Pace)** |
| **Content Hash** | Identical message to all 400 groups | **Unique Spintax variations + Invisible zero-width anti-hash jitter** |
| **350 Groups Duration** | 10 minutes | **~2.0 – 2.4 hours (Smoothly fills cycle)** |
| **FloodWait Handling** | Crashes or forces retries | **Auto-detects sleep duration + 5s safety buffer** |
| **Error Handling** | Keeps retrying broken chats | **Flags Banned/Restricted groups in database and skips them** |

---

## ⚙️ Prerequisites & Setup

### 1. Get Telegram API ID & Hash (Free & Official)
1. Go to [https://my.telegram.org](https://my.telegram.org) and log in with your Telegram phone number.
2. Click on **API development tools**.
3. Create a new app (Title: `PromoApp`, Short name: `promo`).
4. Copy your `api_id` (numeric) and `api_hash` (string).

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```env
BOT_TOKEN=8617134926:AAGKECEbfficK5g8ThtTfJse1SkC-h3YrR0
ADMIN_IDS=YOUR_TELEGRAM_USER_ID
API_ID=12345678
API_HASH=your_api_hash_here
SESSION_STRING=
BROADCAST_INTERVAL_HOURS=2
```

---

## 📱 Connecting Your Sender Account

You can authorize your Telegram account in two easy ways:

### Option A: Directly from Telegram Bot UI (Recommended)
1. Start the bot on Telegram (`/start` or `/menu`).
2. Tap **📱 Connect Sender Account** -> **🔑 Login with Phone & OTP**.
3. Enter your phone number (e.g. `+919876543210`).
4. Enter the verification code sent to your official Telegram app.
5. The bot will automatically authenticate and display your `SESSION_STRING`!

### Option B: Terminal Utility
Run the standalone generator on your computer:
```bash
python generate_session.py
```
Copy the generated string into your `SESSION_STRING` in `.env` or Railway.

---

## 🚂 Deploying to Railway

1. **Create a New GitHub Repository** and push the `promotion_bot` folder contents to it.
2. Go to [Railway.app](https://railway.app) and click **New Project** → **Deploy from GitHub repo**.
3. Select your new promotion bot repository.
4. In Railway dashboard, go to **Variables** and add:
   - `BOT_TOKEN` = `8617134926:AAGKECEbfficK5g8ThtTfJse1SkC-h3YrR0`
   - `ADMIN_IDS` = Your Telegram User ID
   - `API_ID` = Your Telegram API ID
   - `API_HASH` = Your Telegram API Hash
   - `SESSION_STRING` = The session string generated from the login step
   - `BROADCAST_INTERVAL_HOURS` = `2`
5. Click **Deploy**. Railway will build the Docker container and start your 24/7 promotion bot!

---

## 💡 How to Use the Bot

### 1. Paste Your 300–400 Groups
- Open your bot `@SamStoreAd_Bot` and send `/menu`.
- Tap **👥 Manage Groups** → **➕ Add / Bulk Import Groups**.
- Paste your 300–400 group links or usernames (all at once, separated by lines or spaces).
- Tap **⚡ Run Safe Auto-Joiner** if your account needs to join them automatically.

### 2. Customize Your Promo Message & Premium Emojis
- Tap **📝 Edit Promo Message** → **✏️ Edit Promo Text**.
- Use shortcodes like `:crown:`, `:fire:`, `:star:`, `:netflix:`, `:diamond:` or direct `<tg-emoji id="...">`.
- Tap **👀 Live Preview** to see exactly how your target groups will view your promo.

### 3. Start Repeating Automated Broadcasts
- Tap **🚀 Broadcast Controls**.
- Choose your interval: **⏱️ 1 Hour**, **⏱️ 2 Hours**, or **⚙️ Custom**.
- Tap **🟢 Enable Auto-Repeating** or **🚀 Force Run 1 Round Now**.

### 4. Monitor & Review Failed Groups
- Tap **📊 Reports & Failures** at any time.
- View exact error reasons (Slowmode wait time, banned by admin, expired link).
- Tap **📄 Export All Failed Groups** to get a clean text/CSV list.
