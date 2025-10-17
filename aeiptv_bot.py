"""
Telegram Subscription Bot – Minimal, production‑ready example
Library: python-telegram-bot >= 21.0

What it does
------------
• Shows plans with inline buttons (Arabic + English)
• Walks the user through subscription (plan → name → email → payment method)
• Generates an order ID and sends a payment link/QR instructions
• Collects payment confirmation (transaction/reference ID or screenshot note)
• Notifies Admin in DM and posts a compact receipt back to the user
• Simple /status to recall latest order
• Cleanly structured with ConversationHandler and inline keyboards

Environment
-----------
Set these environment variables before running (e.g. in Render, Railway, or .env):
  BOT_TOKEN=<your bot token>
  ADMIN_CHAT_ID=<your Telegram numeric ID>
Optional (leave blank if not used):
  SUPPORT_USERNAME=<your support username without @>
  BRAND_NAME="AEIPTV"                 # used in messages
  PAYMENT_LINK_BASE="https://pay.example.com/invoice/"   # prefix used to build invoice URL

Run locally
-----------
python -m pip install "python-telegram-bot>=21"
python bot.py

Switch to webhook later if you deploy behind HTTPS; this example uses polling for simplicity.
"""
from __future__ import annotations
import os
import random
import string
from dataclasses import dataclass, field
from typing import Dict, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ====== Conversation states
CHOOSING_PLAN, ASK_NAME, ASK_EMAIL, ASK_METHOD, SHOW_INVOICE, WAIT_PAYMENT_PROOF = range(6)

# ====== Models (in-memory for demo; replace with DB/Redis in production)
@dataclass
class Order:
    user_id: int
    order_id: str
    plan_code: str
    plan_title: str
    price_aed: int
    name: Optional[str] = None
    email: Optional[str] = None
    payment_method: Optional[str] = None
    paid_txn_ref: Optional[str] = None


@dataclass
class Store:
    orders: Dict[int, Order] = field(default_factory=dict)  # latest order per user

    def new_order(self, user_id: int, plan_code: str, plan_title: str, price_aed: int) -> Order:
        oid = self._gen_order_id()
        order = Order(user_id=user_id, order_id=oid, plan_code=plan_code, plan_title=plan_title, price_aed=price_aed)
        self.orders[user_id] = order
        return order

    def get(self, user_id: int) -> Optional[Order]:
        return self.orders.get(user_id)

    @staticmethod
    def _gen_order_id(length: int = 8) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "ORD-" + "".join(random.choice(alphabet) for _ in range(length))


STORE = Store()

# ====== Config helpers
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # string ok; telegram lib will cast
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "AE_IPTV")
BRAND = os.environ.get("BRAND_NAME", "AEIPTV")
PAYMENT_LINK_BASE = os.environ.get("PAYMENT_LINK_BASE", "https://pay.example.com/invoice/")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is missing. Set it in your environment.")
if not ADMIN_CHAT_ID:
    raise SystemExit("ADMIN_CHAT_ID is missing. Set it in your environment.")

# ====== Plans (edit freely)
PLANS = [
    {"code": "CASUAL",   "title": "AEIPTV Casual | عادي",      "price_aed": 199, "desc": "1 device • 12 months"},
    {"code": "EXEC",     "title": "AEIPTV Executive | تنفيذي", "price_aed": 299, "desc": "2 devices • 12 months"},
    {"code": "PREMIUM",  "title": "AEIPTV Premium | مميز",     "price_aed": 369, "desc": "All-in-one • 12 months"},
]

PAYMENT_METHODS = [
    ("CARD", "💳 Card / Apple Pay / Google Pay"),
    ("CASHUAE", "💵 Cash / Transfer (UAE)"),
    ("CRYPTO", "🪙 Crypto (USDT)")
]

# ====== Utilities

def make_plans_kb() -> InlineKeyboardMarkup:
    rows = []
    for p in PLANS:
        rows.append([InlineKeyboardButton(f"{p['title']} • {p['price_aed']} AED", callback_data=f"plan:{p['code']}")])
    rows.append([InlineKeyboardButton("Support | الدعم", url=f"https://t.me/{SUPPORT_USERNAME}")])
    return InlineKeyboardMarkup(rows)


def make_payment_methods_kb() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(lbl, callback_data=f"pay:{code}") for code, lbl in PAYMENT_METHODS]
    return InlineKeyboardMarkup([[b] for b in buttons])


def make_paid_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I've paid | دفعت", callback_data=f"paid:{order_id}")],
        [InlineKeyboardButton("Support | الدعم", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])


# ====== Handlers
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"👋 Welcome to {BRAND}!\n\n"
        "Choose a plan to begin:\nاختر الباقة للبدء:"
    )
    await update.effective_chat.send_message(text, reply_markup=make_plans_kb())
    return CHOOSING_PLAN


async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("📦 Plans | الباقات", reply_markup=make_plans_kb())
    return CHOOSING_PLAN


async def on_plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    code = query.data.split(":", 1)[1]
    plan = next((p for p in PLANS if p["code"] == code), None)
    if not plan:
        await query.edit_message_text("Plan not found. Try again.")
        return CHOOSING_PLAN

    order = STORE.new_order(query.from_user.id, plan_code=plan["code"], plan_title=plan["title"], price_aed=plan["price_aed"])
    context.user_data["order_id"] = order.order_id

    text = (
        f"🧾 Order: <b>{order.order_id}</b>\n"
        f"Plan: <b>{order.plan_title}</b> – <b>{order.price_aed} AED</b>\n\n"
        "Please enter your full name (English or Arabic).\n"
        "من فضلك اكتب اسمك الكامل."
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ASK_NAME


async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    order = STORE.get(update.effective_user.id)
    if not order:
        await update.message.reply_text("No active order. Use /start.")
        return ConversationHandler.END
    order.name = name
    await update.message.reply_text(
        "✉️ Great. Now send your email address (for receipts).\n"
        "أرسل بريدك الإلكتروني.")
    return ASK_EMAIL


async def on_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = (update.message.text or "").strip()
    order = STORE.get(update.effective_user.id)
    if not order:
        await update.message.reply_text("No active order. Use /start.")
        return ConversationHandler.END
    order.email = email
    await update.message.reply_text(
        "💰 Choose payment method:\nاختر طريقة الدفع:",
        reply_markup=make_payment_methods_kb(),
    )
    return ASK_METHOD


async def on_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method_code = query.data.split(":", 1)[1]
    order = STORE.get(query.from_user.id)
    if not order:
        await query.edit_message_text("No active order. Use /start.")
        return ConversationHandler.END
    order.payment_method = method_code

    invoice_url = f"{PAYMENT_LINK_BASE}{order.order_id}"
    text = (
        f"🧾 <b>Invoice</b> #{order.order_id}\n"
        f"Plan: <b>{order.plan_title}</b> – <b>{order.price_aed} AED</b>\n"
        f"Method: <b>{method_code}</b>\n\n"
        f"➡️ Pay here: {invoice_url}\n"
        "After paying, tap the button below and send your transaction/reference ID.\n\n"
        "بعد الدفع اضغط الزر بالأسفل وأرسل رقم التحويل/المرجع."
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=make_paid_kb(order.order_id))
    return SHOW_INVOICE


async def on_paid_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order = STORE.get(query.from_user.id)
    if not order:
        await query.edit_message_text("No active order. Use /start.")
        return ConversationHandler.END

    await query.edit_message_text(
        "✅ Great! Please send your payment reference/transaction ID now.\n"
        "أرسل رقم مرجع الدفع الآن.")
    return WAIT_PAYMENT_PROOF


async def on_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ref = (update.message.text or "").strip()
    order = STORE.get(update.effective_user.id)
    if not order:
        await update.message.reply_text("No active order. Use /start.")
        return ConversationHandler.END

    order.paid_txn_ref = ref

    # Notify Admin
    admin_msg = (
        f"🆕 New Subscription\n"
        f"User: @{update.effective_user.username or update.effective_user.id}\n"
        f"Order: {order.order_id}\n"
        f"Plan: {order.plan_title} ({order.plan_code})\n"
        f"Price: {order.price_aed} AED\n"
        f"Name: {order.name}\n"
        f"Email: {order.email}\n"
        f"Method: {order.payment_method}\n"
        f"Txn Ref: {order.paid_txn_ref}"
    )
    try:
        await update.get_bot().send_message(chat_id=int(ADMIN_CHAT_ID), text=admin_msg)
    except Exception as e:
        # Don't crash the flow if admin DM fails
        await update.message.reply_text(f"⚠️ Admin notification failed: {e}")

    # Receipt to user
    receipt = (
        f"🎉 Thank you, {order.name}!\n"
        f"Your order <b>{order.order_id}</b> for <b>{order.plan_title}</b> is being verified.\n"
        "You will receive activation details shortly.\n\n"
        f"شكراً لك! طلبك <b>{order.order_id}</b> قيد المراجعة. سيتم إرسال التفعيل قريباً."
    )
    await update.message.reply_text(receipt, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order = STORE.get(update.effective_user.id)
    if not order:
        await update.message.reply_text("No recent order found. Use /start to begin.")
        return
    text = (
        f"Order: {order.order_id}\n"
        f"Plan: {order.plan_title} – {order.price_aed} AED\n"
        f"Name: {order.name}\nEmail: {order.email}\n"
        f"Method: {order.payment_method}\nTxn: {order.paid_txn_ref or '-'}"
    )
    await update.message.reply_text(text)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Type /start to begin again.")
    return ConversationHandler.END


# ====== App wiring

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start), CommandHandler("plans", show_plans)],
        states={
            CHOOSING_PLAN: [CallbackQueryHandler(on_plan_selected, pattern=r"^plan:")],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)],
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_email)],
            ASK_METHOD: [CallbackQueryHandler(on_payment_method, pattern=r"^pay:")],
            SHOW_INVOICE: [CallbackQueryHandler(on_paid_pressed, pattern=r"^paid:")],
            WAIT_PAYMENT_PROOF: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_payment_proof)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        name="subscription_flow",
        persistent=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("status", cmd_status))

    # Optional: a help command
    async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "/start – begin subscription\n/plans – show plans\n/status – your latest order\n/cancel – cancel current flow\n")

    app.add_handler(CommandHandler("help", cmd_help))

    print("Bot is running… Press Ctrl+C to stop.")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
