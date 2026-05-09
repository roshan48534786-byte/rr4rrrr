import logging
import asyncio
import datetime
import io
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from telegram.error import TelegramError

import config
import database as db
import upi_qr as upi

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_SCREENSHOT = 1
WAITING_UTR        = 2
WAITING_UPI_ID     = 3
WAITING_UPI_NAME   = 4
WAITING_PLAN_KEY   = 5
WAITING_PLAN_NAME  = 6
WAITING_PLAN_PRICE = 7
WAITING_PLAN_DAYS  = 8
WAITING_PLAN_DESC  = 9

# ===============================
#  TIME HELPER
# ===============================

def format_time_remaining(end_time_str):
    """
    End time se remaining time calculate karo — human readable format mein.
    Returns: "6 din 14 ghante 32 minute"
    """
    try:
        end = datetime.datetime.fromisoformat(str(end_time_str))
        now = datetime.datetime.now()
        diff = end - now
        if diff.total_seconds() <= 0:
            return "❌ Expired"
        total_seconds = int(diff.total_seconds())
        days    = total_seconds // 86400
        hours   = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        parts = []
        if days:    parts.append(f"{days} din")
        if hours:   parts.append(f"{hours} ghante")
        if minutes: parts.append(f"{minutes} minute")
        return " ".join(parts) if parts else "1 minute se kam"
    except:
        return "Unknown"

def format_datetime(dt_str):
    try:
        dt = datetime.datetime.fromisoformat(str(dt_str))
        return dt.strftime('%d %b %Y, %I:%M %p')
    except:
        return str(dt_str)

# ===============================
#  KEYBOARDS
# ===============================

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🎬 Get Random Media"],
        ["💳 Subscription (/premium)", "📞 Contact Admin"],
        ["🎁 Refer & Redeem (/refer)", "⏱ My Plan (/status)"]
    ], resize_keyboard=True)

def get_another_inline():
    return InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Get Another", callback_data="get_another")]])

def plan_buttons_inline():
    buttons = []
    for key, plan in config.PLANS.items():
        days = plan['duration_hours'] // 24
        buttons.append([InlineKeyboardButton(
            f"{plan['name']} — ₹{plan['price']} ({days} din)",
            callback_data=f"view_plan_{key}"
        )])
    return InlineKeyboardMarkup(buttons)

def paid_button_inline(plan_key):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Maine Pay Kar Diya", callback_data=f"paid_{plan_key}")],
        [InlineKeyboardButton("🔙 Plans Dekhen", callback_data="show_plans")]
    ])

# ===============================
#  HELPERS
# ===============================

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

async def send_media_to_user(context, chat_id, media):
    try:
        caption = media['caption'] or ""
        if media['file_type'] == 'photo':
            await context.bot.send_photo(chat_id=chat_id, photo=media['file_id'],
                                          caption=caption, reply_markup=get_another_inline())
        elif media['file_type'] == 'video':
            await context.bot.send_video(chat_id=chat_id, video=media['file_id'],
                                          caption=caption, reply_markup=get_another_inline())
        elif media['file_type'] == 'document':
            await context.bot.send_document(chat_id=chat_id, document=media['file_id'],
                                             caption=caption, reply_markup=get_another_inline())
        db.increment_send_count(media['id'])
        return True
    except TelegramError as e:
        logger.error(f"Error sending media: {e}")
        return False

# ===============================
#  BACKGROUND JOBS
# ===============================

async def auto_delete_expired_payments(context: ContextTypes.DEFAULT_TYPE):
    """Har 5 min — 30 min se purane pending payments expire karo"""
    expired = db.get_expired_pending_payments(minutes=30)
    for req in expired:
        try:
            db.update_payment_status(req['id'], 'expired', 0)
            await context.bot.send_message(
                req['user_id'],
                "⏰ *Payment Timeout!*\n\n"
                "Aapki payment 30 minute mein confirm nahi hui isliye automatically delete ho gayi.\n\n"
                "Dobara pay karne ke liye /premium use karein. ✅",
                parse_mode='Markdown',
                reply_markup=main_keyboard()
            )
        except Exception as e:
            logger.error(f"Payment auto-expire error: {e}")

async def check_subscription_expiry(context: ContextTypes.DEFAULT_TYPE):
    """
    Har 30 min check karta hai:
    1. 24 ghante pehle warning bhejta hai
    2. Expire hone par final notification
    """
    # === 24 GHANTE PEHLE WARNING ===
    expiring_soon = db.get_subscriptions_expiring_soon(hours=24)
    for sub in expiring_soon:
        try:
            remaining = format_time_remaining(sub['end_time'])
            end_str   = format_datetime(sub['end_time'])
            await context.bot.send_message(
                sub['user_id'],
                f"⚠️ *Plan Expire Hone Wala Hai!*\n\n"
                f"📋 Plan: *{sub['plan_name']}*\n"
                f"⏳ Bacha time: *{remaining}*\n"
                f"📅 Expire: {end_str}\n\n"
                f"🔄 Renew karne ke liye /premium use karein!\n"
                f"Nahi kiya toh access band ho jaayega. ❌",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Renew Karein", callback_data="show_plans")
                ]])
            )
            db.mark_expiry_notified(sub['id'], level=1)
            logger.info(f"Expiry warning sent to user {sub['user_id']}")
        except Exception as e:
            logger.error(f"Expiry warning error: {e}")

    # === JUST EXPIRED NOTIFICATION ===
    just_expired = db.get_just_expired_subscriptions()
    for sub in just_expired:
        if sub['notified_expiry'] < 2:
            try:
                start_str = format_datetime(sub['start_time'])
                end_str   = format_datetime(sub['end_time'])
                await context.bot.send_message(
                    sub['user_id'],
                    f"❌ *Aapka Plan Expire Ho Gaya!*\n\n"
                    f"📋 Plan: *{sub['plan_name']}*\n"
                    f"📅 Start hua tha: {start_str}\n"
                    f"📅 Expire hua: {end_str}\n"
                    f"⏱ Total duration: *{sub['plan_days']} din*\n\n"
                    f"Premium access band ho gaya. 😢\n\n"
                    f"🔄 *Dobara subscribe karne ke liye:*\n"
                    f"/premium — Nayi subscription lein",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("💳 Dobara Subscribe Karein", callback_data="show_plans")
                    ]])
                )
                db.mark_expiry_notified(sub['id'], level=2)
                logger.info(f"Expiry final notice sent to user {sub['user_id']}")
            except Exception as e:
                logger.error(f"Expiry final notice error: {e}")

# ===============================
#  USER COMMANDS
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referred_by = None

    if args:
        try:
            referred_by = int(args[0])
            if referred_by == user.id:
                referred_by = None
        except:
            referred_by = None

    existing = db.get_user(user.id)
    if not existing:
        db.add_user(user.id, user.username, user.full_name, referred_by)
        if referred_by:
            try:
                await context.bot.send_message(
                    chat_id=referred_by,
                    text=f"🎉 Ek naya user aapke referral se join hua!\n👤 {user.full_name}\n💰 +1 referral credit!"
                )
            except:
                pass

    welcome = config.WELCOME_TEXT.format(bot_name=config.BOT_NAME, free_limit=config.FREE_MEDIA_LIMIT)
    await update.message.reply_text(welcome, reply_markup=main_keyboard())

async def get_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Pehle /start karein!")
        return
    if user['is_banned']:
        await update.message.reply_text("❌ Aapka account ban hai.")
        return

    premium = db.is_premium(user_id)

    # Free user limit check
    if not premium and user['free_used'] >= config.FREE_MEDIA_LIMIT:
        await update.message.reply_text(
            f"❌ *Free Limit Khatam!*\n\n"
            f"Aapko {config.FREE_MEDIA_LIMIT} free videos mil chuki hain.\n\n"
            f"👑 *Premium lein aur unlimited videos enjoy karein!*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"• 7 Days — Unlimited\n"
            f"• 15 Days — Unlimited\n"
            f"• 30 Days — Unlimited",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")
            ]])
        )
        return

    if db.get_media_count() == 0:
        await update.message.reply_text("⚠️ Abhi koi media nahi hai. Baad mein try karein!")
        return

    media = db.get_random_media()
    if not media:
        await update.message.reply_text("Media nahi mila. Dobara try karein!")
        return

    sent = await send_media_to_user(context, update.effective_chat.id, media)
    if sent and not premium:
        db.increment_free_used(user_id)
        used = user['free_used'] + 1
        remaining = config.FREE_MEDIA_LIMIT - used
        if remaining > 0:
            await update.message.reply_text(
                f"📊 Free Videos: {used}/{config.FREE_MEDIA_LIMIT} | ⬜ Bacha: {remaining}\n"
                f"💡 Unlimited ke liye /premium lein!"
            )
        else:
            await update.message.reply_text(
                f"⚠️ *Yeh aapki aakhri free video thi!*\n\n"
                f"Aur videos ke liye premium lein 👇",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")
                ]])
            )

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upi_id, _ = upi.get_upi()
    if not upi_id:
        await update.message.reply_text("⚠️ Admin ne UPI setup nahi kiya abhi.")
        return
    text = (
        "👑 *Premium Plans:*\n\n"
        "✅ Plan choose karein — QR milega\n"
        "✅ Pay karein → Screenshot + UTR bhejein\n"
        "✅ Admin approve karte hi *plan TURANT shuru* ho jaata hai!\n"
        "⏱ Countdown approve hone ke exact waqt se start hota hai."
    )
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=plan_buttons_inline())

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Pehle /start karein!")
        return

    premium = db.is_premium(user_id)
    sub     = db.get_subscription_info(user_id)

    if premium and sub:
        remaining = format_time_remaining(sub['end_time'])
        start_str = format_datetime(sub['start_time'])
        end_str   = format_datetime(sub['end_time'])

        # Progress bar calculate karo
        try:
            start_dt  = datetime.datetime.fromisoformat(str(sub['start_time']))
            end_dt    = datetime.datetime.fromisoformat(str(sub['end_time']))
            now       = datetime.datetime.now()
            total_sec = (end_dt - start_dt).total_seconds()
            used_sec  = (now - start_dt).total_seconds()
            pct       = max(0, min(100, int((used_sec / total_sec) * 100)))
            filled    = pct // 10
            bar       = "🟩" * filled + "⬜" * (10 - filled)
        except:
            bar, pct = "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜", 0

        text = (
            f"👑 *Premium Active!*\n\n"
            f"📋 Plan: *{sub['plan_name']}*\n"
            f"📅 Shuru hua: {start_str}\n"
            f"📅 Khatam hoga: {end_str}\n"
            f"⏳ Bacha: *{remaining}*\n\n"
            f"Progress: {bar} {pct}% used\n\n"
            f"Free used: {user['free_used']}/{config.FREE_MEDIA_LIMIT}\n"
            f"Referral credits: {user['referral_credits']}"
        )
    else:
        text = (
            f"🆓 *Free User*\n\n"
            f"Free used: {user['free_used']}/{config.FREE_MEDIA_LIMIT}\n"
            f"Referral credits: {user['referral_credits']}\n"
            f"Total referrals: {user['total_referrals']}\n\n"
            f"👑 Premium lene ke liye /premium use karein!"
        )

    await update.message.reply_text(text, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")
        ]]) if premium else None
    )

async def refresh_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Refreshed! ✅")
    # Re-use my_status logic
    user_id = query.from_user.id
    user    = db.get_user(user_id)
    premium = db.is_premium(user_id)
    sub     = db.get_subscription_info(user_id)

    if premium and sub:
        remaining = format_time_remaining(sub['end_time'])
        start_str = format_datetime(sub['start_time'])
        end_str   = format_datetime(sub['end_time'])
        try:
            start_dt  = datetime.datetime.fromisoformat(str(sub['start_time']))
            end_dt    = datetime.datetime.fromisoformat(str(sub['end_time']))
            now       = datetime.datetime.now()
            total_sec = (end_dt - start_dt).total_seconds()
            used_sec  = (now - start_dt).total_seconds()
            pct       = max(0, min(100, int((used_sec / total_sec) * 100)))
            filled    = pct // 10
            bar       = "🟩" * filled + "⬜" * (10 - filled)
        except:
            bar, pct = "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜", 0

        text = (
            f"👑 *Premium Active!*\n\n"
            f"📋 Plan: *{sub['plan_name']}*\n"
            f"📅 Shuru hua: {start_str}\n"
            f"📅 Khatam hoga: {end_str}\n"
            f"⏳ Bacha: *{remaining}*\n\n"
            f"Progress: {bar} {pct}% used\n\n"
            f"Referral credits: {user['referral_credits']}"
        )
    else:
        text = "❌ Plan expire ho gaya ya active nahi hai.\n\n/premium se renew karein!"

    try:
        await query.message.edit_text(text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")
            ]])
        )
    except:
        pass

# ===============================
#  PAYMENT FLOW — Screenshot → UTR
# ===============================

async def show_plans_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    upi_id, _ = upi.get_upi()
    if not upi_id:
        await query.message.reply_text("⚠️ UPI setup nahi hua.")
        return
    await query.message.reply_text(
        "👑 *Plan Chunein:*",
        parse_mode='Markdown',
        reply_markup=plan_buttons_inline()
    )

async def view_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("QR generate ho raha hai... ⏳")

    plan_key = query.data.replace("view_plan_", "")
    plan = config.PLANS.get(plan_key)
    if not plan:
        return

    result = upi.get_plan_qr(plan_key, config.PLANS)
    if not result:
        await query.message.reply_text("⚠️ UPI setup nahi hua!")
        return

    qr_buf, upi_id, upi_name, amount = result
    days = plan['duration_hours'] // 24

    caption = (
        f"💳 *{plan['name']} — ₹{plan['price']}*\n\n"
        f"⏱ Duration: *{days} din*\n"
        f"📌 {plan['description']}\n\n"
        f"📲 UPI ID: `{upi_id}`\n"
        f"👤 Name: {upi_name}\n"
        f"💰 Amount: ₹{amount}\n\n"
        f"✅ *Pay karo → Button dabaao → Screenshot + UTR bhejo*\n"
        f"⚡ Approve hote hi countdown TURANT shuru!"
    )

    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=qr_buf,
        caption=caption,
        parse_mode='Markdown',
        reply_markup=paid_button_inline(plan_key)
    )

async def paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.replace("paid_", "")
    plan = config.PLANS.get(plan_key)
    if not plan:
        return

    days = plan['duration_hours'] // 24
    context.user_data['selected_plan'] = plan_key
    await query.message.reply_text(
        f"✅ Plan: *{plan['name']} — {days} Din*\n\n"
        "📸 *Step 1:* Payment screenshot bhejein.",
        parse_mode='Markdown'
    )
    return WAITING_SCREENSHOT

async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_key = context.user_data.get('selected_plan')
    if not plan_key:
        await update.message.reply_text("Pehle /premium se plan select karein.")
        return ConversationHandler.END

    photo    = update.message.photo
    document = update.message.document

    if photo:
        file_id = photo[-1].file_id
    elif document and document.mime_type and document.mime_type.startswith('image'):
        file_id = document.file_id
    else:
        await update.message.reply_text("❌ Sirf image bhejein!")
        return WAITING_SCREENSHOT

    context.user_data['screenshot_file_id'] = file_id
    await update.message.reply_text(
        "✅ Screenshot mila!\n\n"
        "🔢 *Step 2:* UTR Number bhejein.\n"
        "(Payment app → Transaction history → UTR/Ref number)\n\n"
        "Example: `426112345678`",
        parse_mode='Markdown'
    )
    return WAITING_UTR

async def receive_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user      = update.effective_user
    plan_key  = context.user_data.get('selected_plan')
    file_id   = context.user_data.get('screenshot_file_id')
    utr_number = update.message.text.strip()

    if not plan_key or not file_id:
        await update.message.reply_text("❌ /premium se dobara shuru karein.")
        return ConversationHandler.END

    if not (6 <= len(utr_number) <= 25):
        await update.message.reply_text("❌ UTR galat hai! Dobara bhejein (6-25 characters).")
        return WAITING_UTR

    req_id = db.add_payment_request(user.id, plan_key, file_id, utr_number)
    plan   = config.PLANS[plan_key]
    days   = plan['duration_hours'] // 24

    for admin_id in config.ADMIN_IDS:
        try:
            caption = (
                f"💳 *Naya Payment #{req_id}*\n\n"
                f"👤 {user.full_name} (@{user.username})\n"
                f"🆔 `{user.id}`\n"
                f"📋 {plan['name']} — ₹{plan['price']} ({days} din)\n"
                f"🔢 UTR: `{utr_number}`\n"
                f"⏰ {datetime.datetime.now().strftime('%d %b %Y %I:%M %p')}"
            )
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{req_id}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{req_id}")
            ]])
            await context.bot.send_photo(admin_id, photo=file_id, caption=caption,
                                          parse_mode='Markdown', reply_markup=buttons)
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

    await update.message.reply_text(
        f"✅ *Payment Submit Ho Gayi!*\n\n"
        f"📋 Plan: {plan['name']} ({days} din)\n"
        f"🔢 UTR: `{utr_number}`\n\n"
        f"⏳ Admin jald approve karega.\n"
        f"⚡ Approve hote hi aapka *{days} din* ka plan TURANT shuru ho jaayega!\n"
        f"⏰ 30 min mein confirm nahi hua toh auto-delete.",
        parse_mode='Markdown',
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# ===============================
#  APPROVE / REJECT — Countdown Start
# ===============================

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Access denied!")
        return

    req_id = int(query.data.replace("approve_", ""))
    req    = db.get_payment_request(req_id)
    if not req or req['status'] != 'pending':
        await query.answer("Already processed!")
        return

    plan       = config.PLANS.get(req['plan_key'], {})
    hours      = plan.get('duration_hours', 24)
    plan_name  = plan.get('name', req['plan_key'])
    plan_days  = hours // 24

    db.update_payment_status(req_id, 'approved', query.from_user.id)
    # ⚡ Approve hote hi EXACT is second se countdown shuru
    start_time, end_time = db.add_subscription(
        req['user_id'], req['plan_key'], hours,
        query.from_user.id,
        plan_name=plan_name,
        plan_days=plan_days
    )

    await query.answer("✅ Approved! Countdown shuru ho gaya!")
    try:
        await query.message.edit_caption(
            query.message.caption + f"\n\n✅ *APPROVED*\n⏱ {plan_days} din ka countdown shuru!",
            parse_mode='Markdown'
        )
    except:
        pass

    # User ko confirmation + exact timing
    try:
        start_str = format_datetime(start_time)
        end_str   = format_datetime(end_time)
        await context.bot.send_message(
            req['user_id'],
            f"🎉 *Subscription Approved!*\n\n"
            f"📋 Plan: *{plan_name}*\n"
            f"⏱ Duration: *{plan_days} din*\n\n"
            f"⏰ *Shuru:* {start_str}\n"
            f"📅 *Khatam:* {end_str}\n\n"
            f"✅ Countdown ABHI se shuru ho gaya!\n"
            f"📊 Status check: /status\n"
            f"Ab unlimited media enjoy karein! 🎬",
            parse_mode='Markdown',
            reply_markup=main_keyboard()
        )
    except Exception as e:
        logger.error(f"User notify error: {e}")

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Access denied!")
        return

    req_id = int(query.data.replace("reject_", ""))
    req    = db.get_payment_request(req_id)
    if not req or req['status'] != 'pending':
        await query.answer("Already processed!")
        return

    db.update_payment_status(req_id, 'rejected', query.from_user.id)
    await query.answer("❌ Rejected!")
    try:
        await query.message.edit_caption(query.message.caption + "\n\n❌ *REJECTED*", parse_mode='Markdown')
    except:
        pass
    try:
        await context.bot.send_message(
            req['user_id'],
            f"❌ *Payment reject ho gayi.*\nAdmin se contact karein: {config.ADMIN_USERNAME}",
            parse_mode='Markdown'
        )
    except:
        pass

# ===============================
#  OTHER CALLBACKS
# ===============================

async def get_another_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user    = db.get_user(user_id)
    if not user or user['is_banned']:
        return
    premium = db.is_premium(user_id)

    # Free limit check
    if not premium and user['free_used'] >= config.FREE_MEDIA_LIMIT:
        await query.message.reply_text(
            f"❌ *Free Limit Khatam!*\n\n"
            f"Aapko {config.FREE_MEDIA_LIMIT} free videos mil chuki hain.\n\n"
            f"👑 *Premium lein aur unlimited videos enjoy karein!*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")
            ]])
        )
        return

    media = db.get_random_media()
    if not media:
        await query.message.reply_text("Koi media nahi mila!")
        return

    sent = await send_media_to_user(context, query.message.chat_id, media)
    if sent and not premium:
        db.increment_free_used(user_id)
        used = user['free_used'] + 1
        remaining = config.FREE_MEDIA_LIMIT - used
        if remaining > 0:
            await query.message.reply_text(
                f"📊 Free Videos: {used}/{config.FREE_MEDIA_LIMIT} | ⬜ Bacha: {remaining}"
            )
        else:
            await query.message.reply_text(
                f"⚠️ *Yeh aapki aakhri free video thi!*\n\nAur videos ke liye premium lein 👇",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")
                ]])
            )

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user    = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Pehle /start karein!")
        return
    bot_info  = await context.bot.get_me()
    ref_link  = f"https://t.me/{bot_info.username}?start={user_id}"
    credits   = user['referral_credits']
    total_refs = user['total_referrals']
    text = (
        f"🎁 *Referral Program*\n\n"
        f"• 1 referral = *1 credit*\n"
        f"• 1 credit = *{config.REFERRAL_CREDIT_TO_HOURS} hour* premium\n"
        f"• {config.REFERRAL_CREDITS_FOR_DAY} credits = *1 day* premium\n\n"
        f"Stats: {total_refs} referrals | {credits} credits\n\n"
        f"*Referral link:*\n`{ref_link}`"
    )
    buttons = []
    if credits >= config.REFERRAL_CREDITS_FOR_DAY:
        buttons.append([InlineKeyboardButton(
            f"🎉 {config.REFERRAL_CREDITS_FOR_DAY} Credits = 1 Day Redeem", callback_data="redeem_day"
        )])
    if credits >= 1:
        buttons.append([InlineKeyboardButton("⏰ 1 Credit = 1 Hour Redeem", callback_data="redeem_hour")])
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=markup)

async def redeem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "redeem_day":
        if db.use_referral_credits(user_id, config.REFERRAL_CREDITS_FOR_DAY):
            db.add_subscription(user_id, "referral_1day", 24, 0,
                                 plan_name="Referral 1 Day", plan_days=1)
            await query.message.reply_text("🎉 1 Din ka Premium Activate!")
        else:
            await query.message.reply_text("❌ Enough credits nahi!")
    elif query.data == "redeem_hour":
        if db.use_referral_credits(user_id, 1):
            db.add_subscription(user_id, "referral_1hour", config.REFERRAL_CREDIT_TO_HOURS, 0,
                                 plan_name="Referral 1 Hour", plan_days=0)
            await query.message.reply_text(f"🎉 {config.REFERRAL_CREDIT_TO_HOURS} Hour Premium Activate!")
        else:
            await query.message.reply_text("❌ Enough credits nahi!")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 *Admin Contact:*\n\n{config.ADMIN_USERNAME}",
        parse_mode='Markdown'
    )

# ===============================
#  ADMIN COMMANDS
# ===============================

async def adminown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access denied!")
        return
    text = (
        "👑 *ADMIN CONTROL PANEL*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📲 *UPI & QR:*\n"
        "/setupi — UPI ID set/update karo\n"
        "/test_qr — Plans ka QR preview\n\n"
        "💰 *PLANS:*\n"
        "/changeplan — Plan price/duration change karo\n"
        "/plans_list — Saare plans dekho\n\n"
        "🎬 *MEDIA:*\n"
        "/add_media — Media add karo\n"
        "/done — Adding band karo\n"
        "/media_list — Media list\n"
        "/del_media [id] — Delete karo\n\n"
        "💳 *PAYMENTS:*\n"
        "/pending — Pending payments (approve/reject)\n"
        "/give_premium [id] [days] — Manual premium do\n\n"
        "👥 *USERS:*\n"
        "/ban [id] — Ban karo\n"
        "/unban [id] — Unban karo\n"
        "/broadcast — Sab ko message\n\n"
        "📊 *STATS:*\n"
        "/admin — Overview + stats\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ Payment timeout: 30 min\n"
        "🔔 Expiry warning: 24 ghante pehle\n"
        "✅ Countdown: Approve ke exact second se"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access denied!")
        return
    stats      = db.get_stats()
    upi_id, upi_name = upi.get_upi()
    upi_status = f"✅ `{upi_id}` ({upi_name})" if upi_id else "❌ Set nahi hua"
    text = (
        f"🔧 *Admin Panel*\n\n"
        f"👥 Total Users: {stats['total_users']}\n"
        f"🆕 New Today: {stats['new_today']}\n"
        f"👑 Active Subs: {stats['active_subs']}\n"
        f"🎬 Total Media: {stats['total_media']}\n"
        f"💳 Pending: {stats['pending_payments']}\n\n"
        f"UPI: {upi_status}\n\n"
        f"Saare commands: /adminown"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def setup_upi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    upi_id, upi_name = upi.get_upi()
    current = f"\n\nCurrent: `{upi_id}` ({upi_name})" if upi_id else ""
    await update.message.reply_text(
        f"💳 *UPI Setup*{current}\n\nUPI ID bhejein:",
        parse_mode='Markdown'
    )
    return WAITING_UPI_ID

async def receive_upi_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    upi_id = update.message.text.strip()
    if '@' not in upi_id:
        await update.message.reply_text("❌ Sahi UPI ID dein (example: name@paytm)")
        return WAITING_UPI_ID
    context.user_data['new_upi_id'] = upi_id
    await update.message.reply_text(f"✅ `{upi_id}`\n\nAb naam bhejein:", parse_mode='Markdown')
    return WAITING_UPI_NAME

async def receive_upi_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    upi_name = update.message.text.strip()
    upi_id   = context.user_data.get('new_upi_id')
    upi.save_upi(upi_id, upi_name)
    qr_buf = upi.generate_upi_qr(upi_id, upi_name, 10.0, "Test QR")
    await context.bot.send_photo(
        update.effective_chat.id, photo=qr_buf,
        caption=f"✅ *UPI Set!*\nID: `{upi_id}`\nName: {upi_name}",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def test_qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    upi_id, upi_name = upi.get_upi()
    if not upi_id:
        await update.message.reply_text("❌ Pehle /setupi se UPI set karein!")
        return
    for key, plan in config.PLANS.items():
        days   = plan['duration_hours'] // 24
        qr_buf = upi.generate_upi_qr(upi_id, upi_name, plan['price'], f"Bot {plan['name']}")
        await context.bot.send_photo(
            update.effective_chat.id, photo=qr_buf,
            caption=f"*{plan['name']} — ₹{plan['price']} ({days} din)*\nUPI: `{upi_id}`",
            parse_mode='Markdown'
        )

async def plans_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "📋 *Current Plans:*\n\n"
    for key, plan in config.PLANS.items():
        days = plan['duration_hours'] // 24
        text += (
            f"🔑 `{key}` — {plan['name']}\n"
            f"💰 ₹{plan['price']} | ⏱ {days} din ({plan['duration_hours']}h)\n"
            f"📝 {plan['description']}\n\n"
        )
    await update.message.reply_text(text, parse_mode='Markdown')

async def changeplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    keys_text = "\n".join([f"• `{k}` — {v['name']} (₹{v['price']}, {v['duration_hours']//24} din)"
                            for k, v in config.PLANS.items()])
    await update.message.reply_text(
        f"💰 *Plan Change*\n\n{keys_text}\n\nPlan key bhejein:",
        parse_mode='Markdown'
    )
    return WAITING_PLAN_KEY

async def receive_plan_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    key = update.message.text.strip()
    if key not in config.PLANS:
        await update.message.reply_text("❌ Sahi key bhejein.")
        return WAITING_PLAN_KEY
    context.user_data['edit_plan_key'] = key
    await update.message.reply_text(
        f"Plan: *{config.PLANS[key]['name']}*\nNaya naam bhejein (/skip same rakhne ke liye):",
        parse_mode='Markdown'
    )
    return WAITING_PLAN_NAME

async def receive_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    key = context.user_data.get('edit_plan_key')
    val = update.message.text.strip()
    if val != '/skip':
        config.PLANS[key]['name'] = val
    await update.message.reply_text(
        f"Naya price bhejein (current: ₹{config.PLANS[key]['price']}):",
    )
    return WAITING_PLAN_PRICE

async def receive_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    key = context.user_data.get('edit_plan_key')
    val = update.message.text.strip()
    if val != '/skip':
        try:
            config.PLANS[key]['price'] = int(val)
        except:
            await update.message.reply_text("❌ Sirf number dein!")
            return WAITING_PLAN_PRICE
    await update.message.reply_text(
        f"⏱ Duration (days) bhejein (current: {config.PLANS[key]['duration_hours']//24} din):\n"
        f"(e.g. 7 for 7 days, 15 for 15 days, 30 for 30 days)"
    )
    return WAITING_PLAN_DAYS

async def receive_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    key = context.user_data.get('edit_plan_key')
    val = update.message.text.strip()
    if val != '/skip':
        try:
            days = int(val)
            config.PLANS[key]['duration_hours'] = days * 24
        except:
            await update.message.reply_text("❌ Sirf days number dein (e.g. 7, 15, 30)!")
            return WAITING_PLAN_DAYS
    await update.message.reply_text(
        f"📝 Description bhejein (/skip same rakhne ke liye):"
    )
    return WAITING_PLAN_DESC

async def receive_plan_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    key = context.user_data.get('edit_plan_key')
    val = update.message.text.strip()
    if val != '/skip':
        config.PLANS[key]['description'] = val
    plan = config.PLANS[key]
    days = plan['duration_hours'] // 24
    await update.message.reply_text(
        f"✅ *Plan Updated!*\n\n"
        f"`{key}` — {plan['name']}\n"
        f"💰 ₹{plan['price']} | ⏱ {days} din\n"
        f"📝 {plan['description']}\n\n"
        f"⚠️ Permanent change ke liye config.py update karein.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def add_media_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data['adding_media'] = True
    await update.message.reply_text("📤 Photo/Video bhejein. /done karo jab complete ho.")

async def receive_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get('adding_media'):
        return
    caption = update.message.caption or ""
    if update.message.photo:
        file_id, file_type = update.message.photo[-1].file_id, "photo"
    elif update.message.video:
        file_id, file_type = update.message.video.file_id, "video"
    elif update.message.document:
        file_id, file_type = update.message.document.file_id, "document"
    else:
        return
    success = db.add_media(file_id, file_type, caption, update.effective_user.id)
    total   = db.get_media_count()
    msg = f"✅ Added! Total: {total}" if success else f"⚠️ Already exists! Total: {total}"
    await update.message.reply_text(msg)

async def done_adding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data['adding_media'] = False
    await update.message.reply_text(f"✅ Done! Total: {db.get_media_count()}")

async def pending_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    requests = db.get_pending_payments()
    if not requests:
        await update.message.reply_text("✅ Koi pending payment nahi!")
        return
    await update.message.reply_text(f"📋 {len(requests)} pending:")
    for req in requests:
        plan     = config.PLANS.get(req['plan_key'], {})
        days     = plan.get('duration_hours', 24) // 24
        utr_info = f"\n🔢 UTR: `{req['utr_number']}`" if req['utr_number'] else "\n⚠️ UTR: N/A"
        caption  = (
            f"💳 *#{req['id']}*\n"
            f"👤 {req['full_name']} (@{req['username']})\n"
            f"🆔 `{req['user_id']}`\n"
            f"📋 {plan.get('name', '?')} — ₹{plan.get('price', '?')} ({days} din)"
            f"{utr_info}\n"
            f"⏰ {req['requested_at']}"
        )
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{req['id']}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{req['id']}")
        ]])
        try:
            await context.bot.send_photo(update.effective_chat.id, photo=req['screenshot_file_id'],
                                          caption=caption, parse_mode='Markdown', reply_markup=buttons)
        except:
            await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=buttons)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data['broadcasting'] = True
    await update.message.reply_text("📢 Message bhejein (text/photo/video):")

async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get('broadcasting'):
        return
    context.user_data['broadcasting'] = False
    all_users = db.get_all_users()
    success, fail = 0, 0
    await update.message.reply_text(f"📢 {len(all_users)} users ko bhej raha hoon...")
    for user_id in all_users:
        try:
            await update.message.copy(chat_id=user_id)
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    await update.message.reply_text(f"✅ Done!\n✅ {success} success\n❌ {fail} failed")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban [user_id]")
        return
    try:
        target = int(args[0])
        db.ban_user(target)
        await update.message.reply_text(f"✅ {target} banned!")
        await context.bot.send_message(target, "❌ Aapka account ban ho gaya!")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban [user_id]")
        return
    try:
        target = int(args[0])
        db.unban_user(target)
        await update.message.reply_text(f"✅ {target} unbanned!")
        await context.bot.send_message(target, "✅ Account unban! /start karein.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def give_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /give_premium [user_id] [days]")
        return
    try:
        target    = int(args[0])
        days      = int(args[1])
        plan_name = f"Admin Gift {days} Din"
        start_time, end_time = db.add_subscription(
            target, f"manual_{days}day", days * 24,
            update.effective_user.id,
            plan_name=plan_name, plan_days=days
        )
        await update.message.reply_text(
            f"✅ {target} ko {days} din ka premium diya!\n"
            f"⏰ Shuru: {format_datetime(start_time)}\n"
            f"📅 Khatam: {format_datetime(end_time)}"
        )
        await context.bot.send_message(
            target,
            f"🎉 Admin ne aapko *{days} din* ka FREE Premium diya!\n\n"
            f"⏰ Shuru: {format_datetime(start_time)}\n"
            f"📅 Khatam: {format_datetime(end_time)}\n\n"
            f"Enjoy karein! 🎬",
            parse_mode='Markdown',
            reply_markup=main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def media_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    media_list = db.get_all_media(20, 0)
    total      = db.get_media_count()
    if not media_list:
        await update.message.reply_text("Koi media nahi!")
        return
    text = f"🎬 *Media* (Total: {total})\n\n"
    for m in media_list:
        text += f"ID:{m['id']} | {m['file_type']} | Sent:{m['send_count']}x\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def delete_media_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /del_media [id]")
        return
    try:
        db.delete_media(int(args[0]))
        await update.message.reply_text("✅ Deleted!")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ===============================
#  BUTTON HANDLER
# ===============================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🎬 Get Random Media":
        await get_media(update, context)
    elif text == "💳 Subscription (/premium)":
        await premium_command(update, context)
    elif text == "📞 Contact Admin":
        await contact_admin(update, context)
    elif text == "🎁 Refer & Redeem (/refer)":
        await refer_command(update, context)
    elif text == "⏱ My Plan (/status)":
        await my_status(update, context)
    elif is_admin(update.effective_user.id) and context.user_data.get('broadcasting'):
        await receive_broadcast(update, context)

# ===============================
#  MAIN
# ===============================

def main():
    db.init_db()
    upi.init_upi_table()

    app = Application.builder().token(config.BOT_TOKEN).build()

    # Background jobs
    app.job_queue.run_repeating(auto_delete_expired_payments, interval=300,   first=60)   # har 5 min
    app.job_queue.run_repeating(check_subscription_expiry,    interval=1800,  first=120)  # har 30 min

    # Conversations
    upi_conv = ConversationHandler(
        entry_points=[CommandHandler("setupi", setup_upi_command)],
        states={
            WAITING_UPI_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_upi_id)],
            WAITING_UPI_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_upi_name)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    plan_conv = ConversationHandler(
        entry_points=[CommandHandler("changeplan", changeplan_command)],
        states={
            WAITING_PLAN_KEY:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_key)],
            WAITING_PLAN_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_name)],
            WAITING_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_price)],
            WAITING_PLAN_DAYS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_days)],
            WAITING_PLAN_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plan_desc)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    pay_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(paid_callback, pattern=r"^paid_")],
        states={
            WAITING_SCREENSHOT: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_screenshot)],
            WAITING_UTR:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_utr)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    # User commands
    app.add_handler(CommandHandler("start",         start))
    app.add_handler(CommandHandler("premium",       premium_command))
    app.add_handler(CommandHandler("refer",         refer_command))
    app.add_handler(CommandHandler("status",        my_status))
    app.add_handler(CommandHandler("contact_admin", contact_admin))

    # Admin commands
    app.add_handler(CommandHandler("adminown",      adminown_command))
    app.add_handler(CommandHandler("admin",         admin_panel))
    app.add_handler(CommandHandler("add_media",     add_media_command))
    app.add_handler(CommandHandler("done",          done_adding))
    app.add_handler(CommandHandler("pending",       pending_payments))
    app.add_handler(CommandHandler("broadcast",     broadcast_command))
    app.add_handler(CommandHandler("ban",           ban_command))
    app.add_handler(CommandHandler("unban",         unban_command))
    app.add_handler(CommandHandler("give_premium",  give_premium_command))
    app.add_handler(CommandHandler("media_list",    media_list_command))
    app.add_handler(CommandHandler("del_media",     delete_media_command))
    app.add_handler(CommandHandler("test_qr",       test_qr_command))
    app.add_handler(CommandHandler("plans_list",    plans_list_command))

    # Conversations
    app.add_handler(upi_conv)
    app.add_handler(plan_conv)
    app.add_handler(pay_conv)

    # Callbacks
    app.add_handler(CallbackQueryHandler(show_plans_callback,    pattern="^show_plans$"))
    app.add_handler(CallbackQueryHandler(view_plan_callback,     pattern=r"^view_plan_"))
    app.add_handler(CallbackQueryHandler(get_another_callback,   pattern="^get_another$"))
    app.add_handler(CallbackQueryHandler(approve_payment,        pattern=r"^approve_\d+$"))
    app.add_handler(CallbackQueryHandler(reject_payment,         pattern=r"^reject_\d+$"))
    app.add_handler(CallbackQueryHandler(redeem_callback,        pattern=r"^redeem_"))
    app.add_handler(CallbackQueryHandler(refresh_status_callback, pattern="^refresh_status$"))

    # Admin media upload
    app.add_handler(MessageHandler(
        filters.User(config.ADMIN_IDS) & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        receive_admin_media
    ))

    # All text buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    print(f"✅ Bot start! — {config.BOT_NAME}")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
