"""
Telegram Subscription Bot – Render-ready (ENV + .env), ptb>=21
"""

from __future__ import annotations
import os
import random
import string
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

# Optional: load .env for local dev
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ====== Logging
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("subbot")

# ====== Conversation states
CHOOSING_PLAN, ASK_NAME, ASK_EMAIL, ASK_METHOD, SHOW_INVOICE, WAIT_PAYMENT_PROOF = range(6)

# ====== Models
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
    orders: Dict[int, Order] = field(default_factory=dict)

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
def _get_secret(name: str) -> Optional[str]:
    val = os.environ.get(name)
    if val:
        return val.strip()
    file_key = f"{name}_FILE"
    path = os.environ.get(file_key)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.warning("Failed reading %s: %s", file_key, e)
    return None

BOT_TOKEN = _get_secret("BOT_TOKEN")
ADMIN_CHAT_ID = _get_secret("ADMIN_CHAT_ID")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "AE_IPTV").strip()
BRAND = os.environ.get("BRAND_NAME", "AEIPTV").strip()
PAYMENT_LINK_BASE = os.environ.get("PAYMENT_LINK_BASE", "https://pay.example.com/invoice/").strip()

logger.info("Has BOT_TOKEN: %s", bool(BOT_TOKEN))
logger.info("Has ADMIN_CHAT_ID: %s", bool(ADMIN_CHAT_ID))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is missing. Set it in your environment.")
if not ADMIN_CHAT_ID:
    raise SystemExit("ADMIN_CHAT_ID is missing. Set it in your environment.")

# ====== Plans
PLANS = [
    {"code": "CASUAL", "title": "AEIPTV Casual | عادي", "price_aed": 199, "desc": "1 device • 12 months"},
    {"code": "EXEC", "title": "AEIPTV Executive | تنفيذي", "price_aed": 299, "desc": "2 devices • 12 months"},
    {"code": "PREMIUM", "title": "AEIPTV Premium | مميز", "price_aed": 369, "desc": "All-in-one • 12 months"},
]

PAYMENT_METHODS = [
    ("CARD", "💳 Card / Apple Pay / Google Pay"),
    ("CASHUAE", "💵 Cash / Transfer (UAE)"),
    ("CRYPTO", "🪙 Crypto (USDT)")
]

# ====== Keyboards
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
        "Choose a plan to begin:\n"
        "اختر الباقة للبدء:"
    )
    await update.effective_chat.send_message(text, reply_markup=make_plans_kb())
    return CHOOSING_PLAN

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – begin subscription\n/plans – show plans\n/status – your latest order\n/myid – show your chat id\n/cancel – cancel current flow\n"
    )

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your chat ID is: {update.effective_chat.id}")

# … [keep the rest of your handlers unchanged: on_plan_selected, on_name, on_email, etc.] …

# ====== App wiring
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start), CommandHandler("plans", cmd_help)],
        states={
            CHOOSING_PLAN: [CallbackQueryHandler(on_plan_selected, pattern=r"^plan:")],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)],
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_email)],
            ASK_METHOD: [CallbackQueryHandler(on_payment_method, pattern=r"^pay:")],
            SHOW_INVOICE: [CallbackQueryHandler(on_paid_pressed, pattern=r"^paid:")],
            WAIT_PAYMENT_PROOF: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_payment_proof)],
        },
        fallbacks=[CommandHandler("cancel", cmd_help)],
        name="subscription_flow",
        persistent=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("status", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))

    logger.info("Starting bot polling…")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
