# 👑 Premium Telegram Digital Store Bot (OTT & Subscriptions)

A modern, high-converting Telegram Store Bot built with **Python 3.10+**, **aiogram 3.x**, and **Async SQLAlchemy (SQLite)**. Designed for selling digital subscriptions (Netflix, Prime Video, YouTube Premium, AI tools, VPNs, etc.) with instant auto-delivery, dynamic UPI QR payment system, Telegram Premium emoji support, and a complete admin management panel.

---

## 🌟 Key Features

1. **🛍️ Multi-Tier Catalog & Detailed Product Cards**:
   - **Categories** (Streaming Services, VPNs, AI Tools, Education, Gaming, etc.)
   - **Products** with real-time stock indicators (e.g. *Netflix Premium 4K • 10 Available*)
   - **Plans / Variants** with pricing in ₹ (e.g. *1 Month Private Profile • ₹129*, *12 Months • ₹1249*)
   - **Detailed Description Card** (displays features, screen limits, warranty, rules, and price before payment)

2. **⚡ 100% Automated Stock Delivery**:
   - Stores account credentials / license keys securely.
   - Instantly draws from active inventory upon checkout and formats credentials in a copy-to-clipboard code block.
   - Real-time stock decrement and admin sale alerts.

3. **💳 Wallet & Dynamic UPI QR Deposit System**:
   - Preset amounts (₹50, ₹100, ₹200, ₹500, ₹1000, ₹2000) or custom amount input.
   - Generates dynamic, high-resolution QR codes with your UPI ID and exact order amount.
   - Screenshot / 12-digit UTR submission with 1-click admin approval/rejection panel.

4. **⚙️ Complete Admin Management Panel (`/admin`)**:
   - 📊 **Real-time Analytics**: Registered users, total completed orders, gross revenue (₹), today's orders, active inventory count.
   - 📁 **Category Manager**: Add, edit, delete categories.
   - 📦 **Product Manager**: Add products under any category with description and icons.
   - 🏷️ **Variant & Plan Manager**: Add plans, set prices in ₹, and write custom detailed description cards.
   - 🔑 **Bulk Stock Uploader**: Paste multiple accounts line-by-line (`email:password | Pin: 1234`).
   - 💳 **Pending Deposit Approvals**: Approve or reject top-up requests instantly.
   - 📢 **Broadcast Engine**: Dispatch announcements with media to all bot users.
   - 👤 **User Balance Manager**: Look up user by Telegram ID and manually credit/debit balance (+/- ₹).

5. **✨ Telegram Premium Emoji Support**:
   - Full support for `<tg-emoji>` tags.
   - Built-in `/getemoji` command for admins to extract custom emoji IDs directly from Telegram Premium messages.

6. **🎁 Refer & Earn System**:
   - Unique referral links for every customer.
   - Automatic percentage commission on referral purchases.

---

## 🚀 Quick Setup & Deployment

### 1. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
BOT_TOKEN=your_telegram_bot_token_from_botfather
ADMIN_IDS=your_telegram_numeric_id
UPI_ID=your_upi_id@bank
UPI_NAME=OTT Store
CURRENCY_SYMBOL=₹
SUPPORT_USERNAME=@YourSupportHandle
CHANNEL_LINK=https://t.me/your_channel
GROUP_LINK=https://t.me/your_group
REFERRAL_BONUS_PERCENT=5.0
DB_PATH=store.db
```

### 2. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Run Verification Tests
```bash
python3 test_system.py
```

### 4. Start the Bot
```bash
python3 bot.py
```

---

## 📱 Bot Commands

| Command | Audience | Description |
| :--- | :--- | :--- |
| `/start` | Everyone | Opens the store main menu and loads user profile |
| `/start ref_<id>` | Everyone | Start bot with referral tracking |
| `/admin` | Admins Only | Opens the interactive admin dashboard |
| `/getemoji` | Admins Only | Reply to any Premium emoji to extract its `emoji-id` |
