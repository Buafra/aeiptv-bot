"""
AEIPTV Telegram Sales Bot — Rewritten Final

Run anywhere (Render or local). Buttons are robust:
- More Info / Subscribe → packages → Agree → Pay → I Paid
- Always replies even if edit_message_text fails (fallback to send_message)
- Logs every tap; notifies admin on "I Paid"

requirements.txt:
    python-telegram-bot==21.4
"""

import logging
from datetime import datetime
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters
)

# ------------------------- CONFIG (HARDCODED FOR TESTING) -------------------------
BOT_TOKEN = "8399564351:AAFWi6_RHhC-NDtaUFWqcvEGkQSOBn3yI2s"   # <-- YOUR BotFather token
ADMIN_CHAT_ID = 7698278415  # <-- YOUR numeric Telegram ID (from @userinfobot)

# ------------------------- CATALOG -------------------------
PACKAGES: Dict[str, Dict[str, Any]] = {
    "AEIPTV Kids": {
        "code": "kids",
        "price_aed": 70,
        "details": "\n• Kids-safe channels\n• Cartoons & Educational shows\n• Works on 1 device\n",
        "payment_url": "https://buy.stripe.com/3cIbJ29I94yA92g2AV5kk04",
    },
    "AEIPTV Casual": {
        "code": "casual",
        "price_aed": 75,
        "details": "\n• 10,000+ Live Channels\n• 70,000+ Movies (VOD)\n• 12,000+ Series\n• Works on 1 device\n",
        "payment_url": "https://buy.stripe.com/6oU6oIf2t8OQa6kejD5kk03",
    },
    "AEIPTV Executive": {
        "code": "executive",
        "price_aed": 200,
        "details": "\n• 16,000+ Live Channels\n• 24,000+ Movies (VOD)\n• 14,000+ Series\n• Works on 2 devices\n• SD/HD/FHD/4K\n",
        "payment_url": "https://buy.stripe.com/8x23cw07zghi4M0ejD5kk05",
    },
    "AEIPTV Premium": {
        "code": "premium",
        "price_aed": 250,
        "details": "\n• Full combo package\n• 65,000+ Live Channels\n• 180,000+ Movies (VOD)\n• 10,000+ Series\n• Priority support\n",
        "payment_url": "https://buy.stripe.com/eVq00k7A15CE92gdfz5kk01",
    },
}

# Per-user session (simple in-memory)
USER_STATE: Dict[int, Dict[str, Any]] = {}

# ------------------------- TEXTS -------------------------
BRAND = "AEIPTV"
TEXT_WELCOME = f"Welcome to {BRAND}!\n\nHow can we help you today?"
TEXT_MORE_INFO = (
    "📥 How to Watch with 000 Player\n\n"
    "1) Install 000 Player:\n"
    "   • iPhone/iPad: App Store\n"
    "   • Android/TV: Google Play\n"
    "   • Firestick/Android TV (Downloader): http://aftv.news/6913771\n"
    "   • Web (PC, PlayStation, Xbox): https://my.splayer.in\n\n"
    "2) Enter Server Number: 7765\n"
    "3) After payment & activation, you’ll receive login details."
)
TEXT_SUBSCRIBE_PICK = "Please choose a package:"
TEXT_TERMS = (
    "✅ Terms & Notes\n\n"
    "• Activation after payment confirmation.\n"
    "• One account per device unless package allows more.\n"
    "• Using multiple devices may cause buffering or block.\n"
    "• No refunds after activation.\n\n"
    "Do you agree to proceed?"
)
TEXT_PAYMENT_INSTRUCTIONS = "💳 Payment\n\nTap Pay Now to complete payment. Then return and press 'I Paid'."
TEXT_THANK_YOU = f"🎉 Thank you for choosing {BRAND}!\nWe’ll contact you soon to activate your account."

# ------------------------- KEYBOARDS -------------------------
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 More Info", callback_data="more_info"),
         InlineKeyboardButton("💳 Subscribe", callback_data="subscribe")]
    ])

def packages_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(pkg, callback_data=f"pkg|{pkg}")]
            for pkg in PACKAGES.keys()]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="back_home")])
    return InlineKeyboardMarkup(rows)

def agree_kb(pkg_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Agree", callback_data=f"agree|{pkg_name}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="subscribe")]
    ])

def pay_kb(pkg_name: str) -> InlineKeyboardMarkup:
    pay_url = PACKAGES[pkg_name]["payment_url"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Pay Now", url=pay_url)],
        [InlineKeyboardButton("✅ I Paid", callback_data=f"paid|{pkg_name}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="subscribe")]
    ])

# ------------------------- HELPERS -------------------------
async def _safe_edit_or_send(query, context, chat_id: int, text: str,
                             kb: InlineKeyboardMarkup,
                             html: bool = False,
                             no_preview: bool = False) -> None:
    """Try editing the existing message; fallback to sending a new one."""
    try:
        await query.edit_message_text(
            text,
            reply_markup=kb,
            parse_mode="HTML" if html else None,
            disable_web_page_preview=no_preview,
        )
    except Exception as e:
        logging.warning("edit_message_text failed (%s); sending new message.", e)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML" if html else None,
                disable_web_page_preview=no_preview,
            )
        except Exception as e2:
            logging.error("send_message fallback failed: %s", e2)

# ------------------------- HANDLERS -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TEXT_WELCOME, reply_markup=main_menu_kb())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Send any message or use /start.", reply_markup=main_menu_kb())

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TEXT_WELCOME, reply_markup=main_menu_kb())

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # stop spinner
    data = (query.data or "").strip()
    chat_id = query.message.chat.id
    user = query.from_user

    logging.info("Button tapped: data=%s by %s (@%s)", data, user.full_name, user.username)

    if data == "more_info":
        await _safe_edit_or_send(query, context, chat_id, TEXT_MORE_INFO, main_menu_kb(), no_preview=True)
        return

    if data == "subscribe":
        await _safe_edit_or_send(query, context, chat_id, TEXT_SUBSCRIBE_PICK, packages_kb())
        return

    if data == "back_home":
        await _safe_edit_or_send(query, context, chat_id, TEXT_WELCOME, main_menu_kb())
        return

    if data.startswith("pkg|"):
        _, pkg_name = data.split("|", 1)
        pkg = PACKAGES.get(pkg_name)
        if not pkg:
            await _safe_edit_or_send(query, context, chat_id, "Package not found.", packages_kb())
            return
        USER_STATE.setdefault(chat_id, {})["package"] = pkg_name
        text = (
            f"🛍️ <b>{pkg_name}</b>\n"
            f"💰 Price: <b>{pkg['price_aed']} AED</b>\n"
            f"{pkg['details']}\n"
            f"{TEXT_TERMS}"
        )
        await _safe_edit_or_send(query, context, chat_id, text, agree_kb(pkg_name), html=True)
        return

    if data.startswith("agree|"):
        _, pkg_name = data.split("|", 1)
        text = f"You selected <b>{pkg_name}</b>.\n\n{TEXT_PAYMENT_INSTRUCTIONS}"
        await _safe_edit_or_send(query, context, chat_id, text, pay_kb(pkg_name), html=True, no_preview=True)
        return

    if data.startswith("paid|"):
        _, pkg_name = data.split("|", 1)
        selection = USER_STATE.get(chat_id, {}).get("package", pkg_name)
        logging.info("I PAID clicked: user=%s (@%s, id=%s) package=%s",
                     user.full_name, user.username, user.id, selection)

        # Admin notification (best effort)
        if ADMIN_CHAT_ID:
            admin_msg = (
                "🆕 New Payment Confirmation\n\n"
                f"User: @{user.username or 'N/A'} (id: {user.id})\n"
                f"Name: {user.full_name}\n"
                f"Package: {selection}\n"
                f"Time: {datetime.now().isoformat(timespec='seconds')}"
            )
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg)
            except Exception as e:
                logging.error("Failed to notify admin: %s", e)

        await _safe_edit_or_send(query, context, chat_id, TEXT_THANK_YOU, main_menu_kb())
        return

    # Unknown callback → go home
    await _safe_edit_or_send(query, context, chat_id, TEXT_WELCOME, main_menu_kb())

# ------------------------- MAIN -------------------------
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    logging.info("Bot is starting with polling...")
    # accept all updates, drop backlog so buttons feel instant
    app.run_polling(allowed_updates=None, drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
