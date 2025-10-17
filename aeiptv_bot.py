# -*- coding: utf-8 -*-
"""
AEIPTV Telegram Sales Bot — Bilingual (Arabic/English) + Phone Collection + Admin Notifications
Requirements:
    python-telegram-bot==21.4
"""

import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, Contact
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters
)

# ------------------------- CONFIG (HARDCODED FOR TESTING) -------------------------
BOT_TOKEN = "8399564351:AAFbzZRTyVQE76gMMgXCVVshDZgNv9fJO0E"   # <-- Your BotFather token
ADMIN_CHAT_ID = 7698278415  # <-- Your numeric Telegram ID (from @userinfobot)

# ------------------------- PACKAGES -------------------------
PACKAGES: Dict[str, Dict[str, Any]] = {
    "AEIPTV Kids": {
        "code": "kids",
        "price_aed": 70,
        "details_en": "\n• Kids-safe channels\n• Cartoons & Educational shows\n• Works on 1 device\n",
        "details_ar": "\n• قنوات للأطفال\n• كرتون وبرامج تعليمية\n• يعمل على جهاز واحد\n",
        "payment_url": "https://buy.stripe.com/3cIbJ29I94yA92g2AV5kk04",
    },
    "AEIPTV Casual": {
        "code": "casual",
        "price_aed": 75,
        "details_en": "\n• 10,000+ Live Channels\n• 70,000+ Movies (VOD)\n• 12,000+ Series\n• Works on 1 device\n",
        "details_ar": "\n• أكثر من 10,000 قناة مباشرة\n• 70,000+ فيلم (VOD)\n• 12,000+ مسلسل\n• يعمل على جهاز واحد\n",
        "payment_url": "https://buy.stripe.com/6oU6oIf2t8OQa6kejD5kk03",
    },
    "AEIPTV Executive": {
        "code": "executive",
        "price_aed": 200,
        "details_en": "\n• 16,000+ Live Channels\n• 24,000+ Movies (VOD)\n• 14,000+ Series\n• 2 devices • SD/HD/FHD/4K\n",
        "details_ar": "\n• 16,000+ قناة مباشرة\n• 24,000+ فيلم (VOD)\n• 14,000+ مسلسل\n• جهازان • SD/HD/FHD/4K\n",
        "payment_url": "https://buy.stripe.com/8x23cw07zghi4M0ejD5kk05",
    },
    "AEIPTV Premium": {
        "code": "premium",
        "price_aed": 250,
        "details_en": "\n• Full combo package\n• 65,000+ Live Channels\n• 180,000+ Movies (VOD)\n• 10,000+ Series\n• Priority support\n",
        "details_ar": "\n• باقة كاملة شاملة\n• 65,000+ قناة مباشرة\n• 180,000+ فيلم (VOD)\n• 10,000+ مسلسل\n• دعم أولوية\n",
        "payment_url": "https://buy.stripe.com/eVq00k7A15CE92gdfz5kk01",
    },
}

# ------------------------- STATE & STORAGE -------------------------
# chat_id -> {"lang": "ar"/"en", "package": str, "phone": str, "awaiting_phone": bool}
USER_STATE: Dict[int, Dict[str, Any]] = {}
HISTORY_FILE = Path("customers.jsonl")

def save_customer(chat_id: int, user, package: Optional[str], phone: Optional[str]) -> None:
    rec = {
        "chat_id": chat_id,
        "user_id": user.id,
        "username": user.username,
        "name": user.full_name,
        "package": package,
        "phone": phone,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error("Failed to write customers.jsonl: %s", e)

PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{6,}$")

def normalize_phone(s: str) -> str:
    s = s.strip()
    if s.startswith("00"):
        s = "+" + s[2:]
    return re.sub(r"[^\d+]", "", s)

def set_state(chat_id: int, **kv):
    st = USER_STATE.setdefault(chat_id, {})
    st.update(kv)

def get_lang(chat_id: int) -> str:
    return USER_STATE.get(chat_id, {}).get("lang", "ar")  # default Arabic

# ------------------------- I18N STRINGS -------------------------
BRAND = "AEIPTV"
I18N = {
    "pick_lang": {"ar": "اختر اللغة:", "en": "Choose your language:"},
    "lang_ar": {"ar": "العربية", "en": "Arabic"},
    "lang_en": {"ar": "English", "en": "English"},
    "welcome": {
        "ar": f"مرحباً بك في {BRAND}!\n\nكيف نقدر نساعدك اليوم؟",
        "en": f"Welcome to {BRAND}!\n\nHow can we help you today?",
    },
    "more_info_title": {"ar": "📥 طريقة المشاهدة باستخدام 000 Player", "en": "📥 How to Watch with 000 Player"},
    "more_info_body": {
        "ar": (
            "1) ثبّت تطبيق 000 Player:\n"
            "   • iPhone/iPad: App Store\n"
            "   • Android/TV: Google Play\n"
            "   • Firestick/Android TV (Downloader): http://aftv.news/6913771\n"
            "   • Web (PC, PlayStation, Xbox): https://my.splayer.in\n\n"
            "2) أدخل رقم السيرفر: 7765\n"
            "3) بعد الدفع والتفعيل، نرسل لك بيانات الدخول."
        ),
        "en": (
            "1) Install 000 Player:\n"
            "   • iPhone/iPad: App Store\n"
            "   • Android/TV: Google Play\n"
            "   • Firestick/Android TV (Downloader): http://aftv.news/6913771\n"
            "   • Web (PC, PlayStation, Xbox): https://my.splayer.in\n\n"
            "2) Enter Server Number: 7765\n"
            "3) After payment & activation, we will send your login details."
        ),
    },
    "btn_more_info": {"ar": "📋 معلومات", "en": "📋 More Info"},
    "btn_subscribe": {"ar": "💳 اشتراك", "en": "💳 Subscribe"},
    "subscribe_pick": {"ar": "اختر الباقة:", "en": "Please choose a package:"},
    "terms": {
        "ar": (
            "✅ الشروط والملاحظات\n\n"
            "• التفعيل بعد تأكيد الدفع.\n"
            "• حساب واحد لكل جهاز ما لم تذكر الباقة غير ذلك.\n"
            "• الاستخدام على عدة أجهزة قد يسبب تقطيع أو إيقاف الخدمة.\n"
            "• لا توجد استرجاعات بعد التفعيل.\n\n"
            "هل توافق على المتابعة؟"
        ),
        "en": (
            "✅ Terms & Notes\n\n"
            "• Activation after payment confirmation.\n"
            "• One account per device unless package allows more.\n"
            "• Using multiple devices may cause buffering or stop service.\n"
            "• No refunds after activation.\n\n"
            "Do you agree to proceed?"
        ),
    },
    "btn_agree": {"ar": "✅ أوافق", "en": "✅ I Agree"},
    "btn_back": {"ar": "⬅️ رجوع", "en": "⬅️ Back"},
    "payment_instructions": {
        "ar": "💳 الدفع\n\nاضغط (ادفع الآن) لإتمام الدفع. ثم ارجع واضغط (دفعت).",
        "en": "💳 Payment\n\nTap (Pay Now) to complete payment. Then return and press (I Paid).",
    },
    "btn_pay_now": {"ar": "🔗 ادفع الآن", "en": "🔗 Pay Now"},
    "btn_paid": {"ar": "✅ دفعت", "en": "✅ I Paid"},
    "thank_you": {
        "ar": f"🎉 شكراً لاختيارك {BRAND}!\nسنتواصل معك قريباً لتفعيل الخدمة.",
        "en": f"🎉 Thank you for choosing {BRAND}!\nWe’ll contact you soon to activate your account.",
    },
    "breadcrumb_sel": {"ar": "🧩 تم حفظ اختيارك: {pkg} ({price} درهم)", "en": "🧩 Selection saved: {pkg} ({price} AED)"},
    "breadcrumb_agree": {"ar": "✅ وافق على المتابعة: {pkg}", "en": "✅ Agreed to proceed: {pkg}"},
    "breadcrumb_paid": {
        "ar": "🧾 تم الضغط على (دفعت)\n• الباقة: {pkg}\n• الوقت: {ts}",
        "en": "🧾 Payment confirmation clicked\n• Package: {pkg}\n• Time: {ts}",
    },
    "phone_request": {
        "ar": "📞 فضلاً شارك رقم هاتفك للتواصل والتفعيل.\nاضغط (مشاركة رقمي) أو اكتب الرقم مع رمز الدولة (مثال: +9715xxxxxxx).",
        "en": "📞 Please share your phone number so we can contact you to activate.\nTap (Share my number) below, or type it including country code (e.g., +9715xxxxxxx).",
    },
    "btn_share_phone": {"ar": "📲 مشاركة رقمي", "en": "📲 Share my number"},
    "phone_saved": {"ar": "✅ تم حفظ رقمك. سنتواصل معك قريباً.", "en": "✅ Thank you! We saved your number. We'll contact you shortly."},
    "phone_invalid": {
        "ar": "❗️الرقم غير صحيح. اكتب الرقم مع رمز الدولة (مثال: +9715xxxxxxx) أو اضغط (مشاركة رقمي).",
        "en": "❗️That doesn’t look valid. Include country code (e.g., +9715xxxxxxx), or tap (Share my number).",
    },
}

def t(chat_id: int, key: str) -> str:
    lang = get_lang(chat_id)
    val = I18N.get(key)
    if isinstance(val, dict):
        return val.get(lang, val.get("en", ""))
    return str(val)

# ------------------------- KEYBOARDS -------------------------
def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N["lang_ar"]["ar"], callback_data="lang|ar"),
         InlineKeyboardButton(I18N["lang_en"]["en"], callback_data="lang|en")]
    ])

def main_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(chat_id, "btn_more_info"), callback_data="more_info"),
         InlineKeyboardButton(t(chat_id, "btn_subscribe"), callback_data="subscribe")]
    ])

def packages_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(pkg, callback_data=f"pkg|{pkg}")] for pkg in PACKAGES.keys()]
    rows.append([InlineKeyboardButton(I18N["btn_back"]["ar"] + " / " + I18N["btn_back"]["en"], callback_data="back_home")])
    return InlineKeyboardMarkup(rows)

def agree_kb(chat_id: int, pkg_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(chat_id, "btn_agree"), callback_data=f"agree|{pkg_name}")],
        [InlineKeyboardButton(t(chat_id, "btn_back"), callback_data="subscribe")],
    ])

def pay_kb(chat_id: int, pkg_name: str) -> InlineKeyboardMarkup:
    pay_url = PACKAGES[pkg_name]["payment_url"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(chat_id, "btn_pay_now"), url=pay_url)],
        [InlineKeyboardButton(t(chat_id, "btn_paid"), callback_data=f"paid|{pkg_name}")],
        [InlineKeyboardButton(t(chat_id, "btn_back"), callback_data="subscribe")],
    ])

def phone_request_kb(chat_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t(chat_id, "btn_share_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Tap to share, or type your number…"
    )

# ------------------------- HELPERS -------------------------
async def safe_edit_or_send(query, context, chat_id: int, text: str,
                            kb, html: bool = False, no_preview: bool = False) -> None:
    """Try editing; if it fails, send a new message."""
    try:
        await query.edit_message_text(
            text,
            reply_markup=kb if isinstance(kb, InlineKeyboardMarkup) else None,
            parse_mode="HTML" if html else None,
            disable_web_page_preview=no_preview,
        )
        if isinstance(kb, ReplyKeyboardMarkup):
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=kb,
                parse_mode="HTML" if html else None, disable_web_page_preview=no_preview
            )
    except Exception as e:
        logging.warning("edit_message_text failed (%s); sending new message.", e)
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=kb,
                parse_mode="HTML" if html else None, disable_web_page_preview=no_preview,
            )
        except Exception as e2:
            logging.error("send_message fallback failed: %s", e2)

def pkg_details_for_lang(pkg_name: str, lang: str) -> str:
    pkg = PACKAGES[pkg_name]
    return pkg["details_ar"] if lang == "ar" else pkg["details_en"]

# ------------------------- HANDLERS -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(t(chat_id, "pick_lang"), reply_markup=lang_kb())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

async def any_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    st = USER_STATE.get(chat_id, {})
    txt = (update.message.text or "").strip()

    if st.get("awaiting_phone") and txt:
        if PHONE_RE.match(txt):
            phone = normalize_phone(txt)
            set_state(chat_id, phone=phone, awaiting_phone=False)
            save_customer(chat_id, update.effective_user, st.get("package"), phone)
            if ADMIN_CHAT_ID:
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=(f"📞 Phone captured\n"
                              f"User: @{update.effective_user.username or 'N/A'} (id: {update.effective_user.id})\n"
                              f"Name: {update.effective_user.full_name}\n"
                              f"Package: {st.get('package')}\n"
                              f"Phone: {phone}")
                    )
                except Exception as e:
                    logging.error("Admin notify (phone) failed: %s", e)
            await update.message.reply_text(t(chat_id, "phone_saved"), reply_markup=ReplyKeyboardRemove())
            await update.message.reply_text(t(chat_id, "thank_you"), reply_markup=main_menu_kb(chat_id))
            return
        else:
            await update.message.reply_text(t(chat_id, "phone_invalid"), reply_markup=phone_request_kb(chat_id))
            return

    if "lang" not in st:
        await update.message.reply_text(t(chat_id, "pick_lang"), reply_markup=lang_kb())
    else:
        await update.message.reply_text(t(chat_id, "welcome"), reply_markup=main_menu_kb(chat_id))

async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    contact: Contact = update.message.contact
    phone = normalize_phone(contact.phone_number or "")
    set_state(chat_id, phone=phone, awaiting_phone=False)
    st = USER_STATE.get(chat_id, {})
    save_customer(chat_id, update.effective_user, st.get("package"), phone)

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(f"📞 Phone captured via Contact\n"
                      f"User: @{update.effective_user.username or 'N/A'} (id: {update.effective_user.id})\n"
                      f"Name: {update.effective_user.full_name}\n"
                      f"Package: {st.get('package')}\n"
                      f"Phone: {phone}")
            )
        except Exception as e:
            logging.error("Admin notify (contact) failed: %s", e)

    await update.message.reply_text(t(chat_id, "phone_saved"), reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(t(chat_id, "thank_you"), reply_markup=main_menu_kb(chat_id))

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    user = query.from_user
    data = (query.data or "").strip()

    logging.info("Button tapped: %s by %s (@%s)", data, user.full_name, user.username)

    if data.startswith("lang|"):
        _, lang = data.split("|", 1)
        if lang not in ("ar", "en"):
            lang = "ar"
        set_state(chat_id, lang=lang)
        await safe_edit_or_send(query, context, chat_id, t(chat_id, "welcome"), main_menu_kb(chat_id))
        return

    if "lang" not in USER_STATE.get(chat_id, {}):
        await safe_edit_or_send(query, context, chat_id, t(chat_id, "pick_lang"), lang_kb())
        return

    if data == "more_info":
        text = t(chat_id, "more_info_title") + "\n\n" + t(chat_id, "more_info_body")
        await safe_edit_or_send(query, context, chat_id, text, main_menu_kb(chat_id), no_preview=True)
        return

    if data == "subscribe":
        await safe_edit_or_send(query, context, chat_id, t(chat_id, "subscribe_pick"), packages_kb())
        return

    if data == "back_home":
        await safe_edit_or_send(query, context, chat_id, t(chat_id, "welcome"), main_menu_kb(chat_id))
        return

    if data.startswith("pkg|"):
        _, pkg_name = data.split("|", 1)
        if pkg_name not in PACKAGES:
            await safe_edit_or_send(query, context, chat_id, "Package not found.", packages_kb())
            return
        set_state(chat_id, package=pkg_name)
        price = PACKAGES[pkg_name]["price_aed"]
        await context.bot.send_message(chat_id=chat_id, text=t(chat_id, "breadcrumb_sel").format(pkg=pkg_name, price=price))
        lang = get_lang(chat_id)
        details = pkg_details_for_lang(pkg_name, lang)
        text = f"🛍️ <b>{pkg_name}</b>\n💰 <b>{price} AED</b>\n{details}\n{t(chat_id, 'terms')}"
        await safe_edit_or_send(query, context, chat_id, text, agree_kb(chat_id, pkg_name), html=True)
        return

    if data.startswith("agree|"):
        _, pkg_name = data.split("|", 1)
        await context.bot.send_message(chat_id=chat_id, text=t(chat_id, "breadcrumb_agree").format(pkg=pkg_name))
        text = f"{t(chat_id, 'payment_instructions')}"
        await safe_edit_or_send(query, context, chat_id, text, pay_kb(chat_id, pkg_name), no_preview=True)
        return

    if data.startswith("paid|"):
        _, pkg_name = data.split("|", 1)
        selection = USER_STATE.get(chat_id, {}).get("package", pkg_name)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await context.bot.send_message(chat_id=chat_id, text=t(chat_id, "breadcrumb_paid").format(pkg=selection, ts=ts))

        set_state(chat_id, awaiting_phone=True)
        await context.bot.send_message(chat_id=chat_id, text=t(chat_id, "phone_request"), reply_markup=phone_request_kb(chat_id))

        if ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=(f"🆕 I Paid clicked (phone pending)\n"
                          f"User: @{user.username or 'N/A'} (id: {user.id})\n"
                          f"Name: {user.full_name}\n"
                          f"Package: {selection}\n"
                          f"Phone: pending")
                )
            except Exception as e:
                logging.error("Admin notify (pre-phone) failed: %s", e)
        return

    await safe_edit_or_send(query, context, chat_id, t(chat_id, "welcome"), main_menu_kb(chat_id))

# ------------------------- MAIN -------------------------
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.CONTACT, on_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_text))

    logging.info("Bot is starting with polling...")
    app.run_polling(allowed_updates=None, drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
