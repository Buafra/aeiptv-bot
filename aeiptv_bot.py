"""
Telegram Subscription Bot – Render-ready (ENV + .env), ptb>=21
Complete implementation with all handlers
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

# Debug logging
logger.info("Has BOT_TOKEN: %s", bool(BOT_TOKEN))
logger.info("Has ADMIN_CHAT_ID: %s", bool(ADMIN_CHAT_ID))
logger.info("BOT_TOKEN length: %s", len(BOT_TOKEN) if BOT_TOKEN else 0)
logger.info("All env vars: %s", list(os.environ.keys()))

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

# ====== Helper functions
def get_plan_by_code(code: str) -> Optional[dict]:
    for p in PLANS:
        if p["code"] == code:
            return p
    return None

def get_payment_method_label(code: str) -> str:
    for c, lbl in PAYMENT_METHODS:
        if c == code:
            return lbl
    return code

# ====== Handlers
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"👋 Welcome to {BRAND}!\n\n"
        "Choose a plan to begin:\n"
        "اختر الباقة للبدء:"
    )
    await update.effective_chat.send_message(text, reply_markup=make_plans_kb())
    return CHOOSING_PLAN

async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📺 {BRAND} Plans | الباقات\n\n"
        "Choose your subscription:\n"
        "اختر اشتراكك:"
    )
    await update.message.reply_text(text, reply_markup=make_plans_kb())
    return CHOOSING_PLAN

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – begin subscription | ابدأ الاشتراك\n"
        "/plans – show plans | عرض الباقات\n"
        "/status – your latest order | طلبك الأخير\n"
        "/myid – show your chat id | معرف الدردشة\n"
        "/cancel – cancel current flow | إلغاء"
    )

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your chat ID is: {update.effective_chat.id}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    order = STORE.get(user_id)
    
    if not order:
        await update.message.reply_text(
            "❌ No order found | لا يوجد طلب\n\n"
            "Use /start to create a new subscription."
        )
        return
    
    status_text = (
        f"📋 Order Status | حالة الطلب\n\n"
        f"Order ID: {order.order_id}\n"
        f"Plan: {order.plan_title}\n"
        f"Price: {order.price_aed} AED\n"
        f"Name: {order.name or 'Not provided'}\n"
        f"Email: {order.email or 'Not provided'}\n"
        f"Payment: {get_payment_method_label(order.payment_method) if order.payment_method else 'Not selected'}\n"
        f"Status: {'✅ Paid (pending verification)' if order.paid_txn_ref else '⏳ Awaiting payment'}"
    )
    await update.message.reply_text(status_text)

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Cancelled | تم الإلغاء\n\n"
        "Use /start to begin again."
    )
    return ConversationHandler.END

# ====== Conversation handlers
async def on_plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_code = query.data.split(":")[1]
    plan = get_plan_by_code(plan_code)
    
    if not plan:
        await query.message.reply_text("❌ Invalid plan | باقة غير صالحة")
        return ConversationHandler.END
    
    # Create new order
    user_id = update.effective_user.id
    order = STORE.new_order(user_id, plan_code, plan["title"], plan["price_aed"])
    
    logger.info("User %s selected plan %s, order %s", user_id, plan_code, order.order_id)
    
    await query.message.reply_text(
        f"✅ Selected: {plan['title']}\n"
        f"💰 Price: {plan['price_aed']} AED\n"
        f"📝 {plan['desc']}\n\n"
        f"Please enter your full name:\n"
        f"الرجاء إدخال اسمك الكامل:"
    )
    
    return ASK_NAME

async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    order = STORE.get(user_id)
    
    if not order:
        await update.message.reply_text("❌ Session expired. Use /start to begin again.")
        return ConversationHandler.END
    
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("❌ Name too short. Please enter your full name:")
        return ASK_NAME
    
    order.name = name
    logger.info("Order %s: name set to %s", order.order_id, name)
    
    await update.message.reply_text(
        f"✅ Name: {name}\n\n"
        f"Now, please enter your email address:\n"
        f"الآن، الرجاء إدخال بريدك الإلكتروني:"
    )
    
    return ASK_EMAIL

async def on_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    order = STORE.get(user_id)
    
    if not order:
        await update.message.reply_text("❌ Session expired. Use /start to begin again.")
        return ConversationHandler.END
    
    email = update.message.text.strip()
    
    # Basic email validation
    if "@" not in email or "." not in email or len(email) < 5:
        await update.message.reply_text("❌ Invalid email. Please enter a valid email address:")
        return ASK_EMAIL
    
    order.email = email
    logger.info("Order %s: email set to %s", order.order_id, email)
    
    await update.message.reply_text(
        f"✅ Email: {email}\n\n"
        f"Choose your payment method:\n"
        f"اختر طريقة الدفع:",
        reply_markup=make_payment_methods_kb()
    )
    
    return ASK_METHOD

async def on_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    order = STORE.get(user_id)
    
    if not order:
        await query.message.reply_text("❌ Session expired. Use /start to begin again.")
        return ConversationHandler.END
    
    method_code = query.data.split(":")[1]
    order.payment_method = method_code
    
    logger.info("Order %s: payment method set to %s", order.order_id, method_code)
    
    # Generate invoice details based on payment method
    if method_code == "CARD":
        payment_instructions = (
            f"💳 Card Payment Instructions\n\n"
            f"Payment Link: {PAYMENT_LINK_BASE}{order.order_id}\n\n"
            f"Or scan QR code (if available)\n\n"
            f"After payment, click 'I've paid' below."
        )
    elif method_code == "CASHUAE":
        payment_instructions = (
            f"💵 Cash/Transfer Payment (UAE)\n\n"
            f"Bank: [Your Bank Name]\n"
            f"Account: [Account Number]\n"
            f"IBAN: [IBAN Number]\n"
            f"Amount: {order.price_aed} AED\n\n"
            f"Reference: {order.order_id}\n\n"
            f"After payment, click 'I've paid' and send proof."
        )
    else:  # CRYPTO
        payment_instructions = (
            f"🪙 Crypto Payment (USDT)\n\n"
            f"Network: TRC20 (Tron)\n"
            f"Address: [Your USDT Address]\n"
            f"Amount: ${order.price_aed // 3.67:.2f} USDT\n\n"
            f"Reference: {order.order_id}\n\n"
            f"After payment, click 'I've paid' and send transaction hash."
        )
    
    invoice_text = (
        f"📋 Invoice | الفاتورة\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Order ID: {order.order_id}\n"
        f"Plan: {order.plan_title}\n"
        f"Name: {order.name}\n"
        f"Email: {order.email}\n"
        f"Amount: {order.price_aed} AED\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"{payment_instructions}"
    )
    
    await query.message.reply_text(invoice_text, reply_markup=make_paid_kb(order.order_id))
    
    return SHOW_INVOICE

async def on_paid_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    order = STORE.get(user_id)
    
    if not order:
        await query.message.reply_text("❌ Session expired. Use /start to begin again.")
        return ConversationHandler.END
    
    await query.message.reply_text(
        f"✅ Great! Please send your payment proof:\n\n"
        f"• Transaction screenshot\n"
        f"• Transaction ID/Reference\n"
        f"• Receipt photo\n\n"
        f"الرجاء إرسال إثبات الدفع:"
    )
    
    return WAIT_PAYMENT_PROOF

async def on_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    order = STORE.get(user_id)
    
    if not order:
        await update.message.reply_text("❌ Session expired. Use /start to begin again.")
        return ConversationHandler.END
    
    # Get proof (text or photo)
    if update.message.photo:
        proof = f"Photo: {update.message.photo[-1].file_id}"
    else:
        proof = update.message.text.strip()
    
    order.paid_txn_ref = proof
    logger.info("Order %s: payment proof received", order.order_id)
    
    # Send notification to admin
    try:
        admin_message = (
            f"🔔 NEW ORDER | طلب جديد\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Order ID: {order.order_id}\n"
            f"Plan: {order.plan_title}\n"
            f"Price: {order.price_aed} AED\n"
            f"Name: {order.name}\n"
            f"Email: {order.email}\n"
            f"Payment: {get_payment_method_label(order.payment_method)}\n"
            f"User: @{update.effective_user.username or 'N/A'} ({user_id})\n"
            f"Proof: {proof[:100]}\n"
            f"━━━━━━━━━━━━━━━━"
        )
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message)
        
        # If photo, forward it too
        if update.message.photo:
            await update.message.forward(chat_id=ADMIN_CHAT_ID)
        
        logger.info("Admin notification sent for order %s", order.order_id)
    except Exception as e:
        logger.error("Failed to notify admin: %s", e)
    
    # Confirm to user
    await update.message.reply_text(
        f"✅ Payment proof received!\n\n"
        f"🎉 Thank you for your order!\n"
        f"Order ID: {order.order_id}\n\n"
        f"Our team will verify your payment and activate your subscription within 1-24 hours.\n\n"
        f"You will receive your credentials via email: {order.email}\n\n"
        f"Need help? Contact @{SUPPORT_USERNAME}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"شكراً لطلبك! سيتم التفعيل خلال 1-24 ساعة"
    )
    
    return ConversationHandler.END

# ====== App wiring
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("plans", cmd_plans)
        ],
        states={
            CHOOSING_PLAN: [CallbackQueryHandler(on_plan_selected, pattern=r"^plan:")],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)],
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_email)],
            ASK_METHOD: [CallbackQueryHandler(on_payment_method, pattern=r"^pay:")],
            SHOW_INVOICE: [CallbackQueryHandler(on_paid_pressed, pattern=r"^paid:")],
            WAIT_PAYMENT_PROOF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_payment_proof),
                MessageHandler(filters.PHOTO, on_payment_proof)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        name="subscription_flow",
        persistent=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))

    logger.info("🚀 Bot started successfully!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()