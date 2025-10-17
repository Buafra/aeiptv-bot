"""
AEIPTV Telegram Sales Bot

Features
- Replies to ANY message with a menu: [More Info] [Subscribe]
- Subscribe → choose package → show price & terms → ask to Agree → show payment link
- After user taps [I Paid], bot notifies ADMIN and thanks the user
- Includes /start and /help

Requirements
- python-telegram-bot >= 20.0

Setup
1) pip install python-telegram-bot==21.4
2) Set environment variables:
   BOT_TOKEN="123456:ABC..."
   ADMIN_CHAT_ID="123456789"   # Your Telegram numeric chat id
3) Edit the PACKAGES dict below with your real prices and payment links
4) Run: python aeiptv_bot.py

Notes
- This script uses polling for simplicity. For production, configure a webhook.
- All texts are in English. You can Arabic‑ize easily by editing the TEXT_* strings.
"""

from __future__ import annotations
import os
import logging
from datetime import datetime
from typing import Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ------------------------- CONFIG -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT-YOUR-TOKEN-HERE")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))  # your Telegram user/chat id

# TODO: Replace prices and payment links with your real ones
PACKAGES: Dict[str, Dict[str, Any]] = {
    "AEIPTV Casual": {
        "code": "casual",
        "price_aed": 199,  # TODO
        "details": "\n• 10,000+ Live Channels\n• 70,000+ Movies (VOD)\n• 12,000+ Series\n• Works on 1 device\n",
        "payment_url": "https://your-payment-link.example/casual",  # TODO
    },
    "AEIPTV Executive": {
        "code": "executive",
        "price_aed": 269,  # TODO
        "details": "\n• 16,000+ Live Channels\n• 24,000+ Movies (VOD)\n• 14,000+ Series\n• SD/HD/FHD/4K\n• Works on 2 devices\n",
        "payment_url": "https://your-payment-link.example/executive",  # TODO
    },
    "AEIPTV Premium": {
        "code": "premium",
        "price_aed": 369,  # TODO
        "details": "\n• Full package combo\n• 65,000+ Live Channels\n• 180,000+ Movies (VOD)\n• 10,000+ Series\n• Priority support\n",
        "payment_url": "https://your-payment-link.example/premium",  # TODO
    },
}

# Simple per-user session state (in-memory)
USER_STATE: Dict[int, Dict[str, Any]] = {}

# ----------------------- TEXT STRINGS ---------------------
BRAND = "AEIPTV"

TEXT_WELCOME = (
    f"Welcome to {BRAND}!\n\n"
    "How can we help you today?"
)

TEXT_MORE_INFO = (
    "📥 How to Watch with 000 Player\n\n"
    "1) Install 000 Player on your device:\n"
    "   • iPhone/iPad: App Store\n"
    "   • Android/TV: Google Play\n"
    "   • Firestick/Android TV via Downloader: http://aftv.news/6913771\n"
    "   • Web Player (PC/Laptop, PlayStation, Xbox): https://my.splayer.in\n\n"
    "2) Open the app and enter the Server Number in Host/DNS field: 7765\n"
    "3) After payment & activation, we will send your login details."
)

TEXT_SUBSCRIBE_PICK = "Please choose a package:"

TEXT_TERMS = (
    "✅ Terms & Notes\n\n"
    "• Activation after payment confirmation.\n"
    "• One account per device limit unless the package states otherwise.\n"
    "• Using on multiple devices simultaneously may cause buffering or stop working.\n"
    "• No refunds after activation.\n\n"
    "Do you agree to proceed?"
)

TEXT_PAYMENT_INSTRUCTIONS = (
    "💳 Payment\n\n"
    "Tap the button below to pay. After completing payment, come back and press ‘I Paid’."
)

TEXT_THANK_YOU = (
    f"🎉 Thank you for choosing {BRAND}!\n"
    "We’ll message you shortly to finalize your activation."
)

# ---------------------- KEYBOARD HELPERS ------------------

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📋 More Info", callback_data="more_info"),
                InlineKeyboardButton("💳 Subscribe", callback_data="subscribe"),
            ]
        ]
    )


def packages_kb() -> InlineKeyboardMarkup:
    rows = []
    for pkg_name in PACKAGES.keys():
        rows.append([InlineKeyboardButton(pkg_name, callback_data=f"pkg|{pkg_name}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="back_home")])
    return InlineKeyboardMarkup(rows)


def agree_kb(pkg_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Agree", callback_data=f"agree|{pkg_name}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="subscribe")],
    ])


def pay_kb(pkg_name: str) -> InlineKeyboardMarkup:
    pay_url = PACKAGES[pkg_name]["payment_url"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Pay Now", url=pay_url)],
        [InlineKeyboardButton("✅ I Paid", callback_data=f"paid|{pkg_name}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="subscribe")],
    ])

# ------------------------- HANDLERS -----------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    USER_STATE.setdefault(chat_id, {})
    await update.effective_message.reply_text(TEXT_WELCOME, reply_markup=main_menu_kb())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send any message to see the menu, or use /start.",
        reply_markup=main_menu_kb(),
    )


async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Reply to ANY incoming text with the main menu
    chat_id = update.effective_chat.id
    USER_STATE.setdefault(chat_id, {})
    await update.message.reply_text(TEXT_WELCOME, reply_markup=main_menu_kb())


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "more_info":
        await query.edit_message_text(TEXT_MORE_INFO, reply_markup=main_menu_kb(), disable_web_page_preview=True)
        return

    if data == "subscribe":
        await query.edit_message_text(TEXT_SUBSCRIBE_PICK, reply_markup=packages_kb())
        return

    if data == "back_home":
        await query.edit_message_text(TEXT_WELCOME, reply_markup=main_menu_kb())
        return

    if data.startswith("pkg|"):
        _, pkg_name = data.split("|", 1)
        pkg = PACKAGES.get(pkg_name)
        if not pkg:
            await query.edit_message_text("Package not found.", reply_markup=packages_kb())
            return

        # Save selection in state
        chat_id = query.message.chat.id
        USER_STATE.setdefault(chat_id, {})["package"] = pkg_name

        text = (
            f"🛍️ <b>{pkg_name}</b>\n"
            f"💰 Price: <b>{pkg['price_aed']} AED</b>\n"
            f"{pkg['details']}\n"
            f"{TEXT_TERMS}"
        )
        await query.edit_message_text(text, reply_markup=agree_kb(pkg_name), parse_mode="HTML")
        return

    if data.startswith("agree|"):
        _, pkg_name = data.split("|", 1)
        # show payment link
        text = (
            f"You selected <b>{pkg_name}</b>.\n\n"
            f"{TEXT_PAYMENT_INSTRUCTIONS}"
        )
        await query.edit_message_text(text, reply_markup=pay_kb(pkg_name), parse_mode="HTML", disable_web_page_preview=True)
        return

    if data.startswith("paid|"):
        _, pkg_name = data.split("|", 1)
        user = query.from_user
        chat_id = query.message.chat.id
        selection = USER_STATE.get(chat_id, {}).get("package", pkg_name)

        # Log to terminal for visibility
        logging.info(
            "I PAID clicked: user=%s (@%s, id=%s) package=%s",
            user.full_name, user.username, user.id, selection,
        )

        # Notify admin (best-effort)
      # Notify admin (best-effort)
if ADMIN_CHAT_ID and isinstance(ADMIN_CHAT_ID, int) and ADMIN_CHAT_ID != 123456789:
    msg_admin = (
        "🆕 New Payment Confirmation\n\n"
        f"User: @{user.username or 'N/A'} (id: {user.id})\n"
        f"Name: {user.full_name}\n"
        f"Package: {selection}\n"
        f"Time: {datetime.now().isoformat(timespec='seconds')}"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg_admin)
    except Exception as e:
        logging.error("Failed to notify admin: %s", e)


        # Thank the user – fall back to sending a new message if edit fails
        try:
            await query.edit_message_text(TEXT_THANK_YOU, reply_markup=main_menu_kb())
        except Exception as e:
            logging.warning("edit_message_text failed (sending new message): %s", e)
            try:
                await context.bot.send_message(chat_id=chat_id, text=TEXT_THANK_YOU, reply_markup=main_menu_kb())
            except Exception as e2:
                logging.error("Failed to send thank-you message: %s", e2)
        return


# -------------------------- MAIN --------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    if not BOT_TOKEN or BOT_TOKEN == "PUT-YOUR-TOKEN-HERE":
        raise SystemExit("Please set BOT_TOKEN env var.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    logging.info("Bot is starting with polling...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
