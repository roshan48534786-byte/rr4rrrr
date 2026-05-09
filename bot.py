"""
╔══════════════════════════════════════════════════════╗
║         TELEGRAM CONTENT BOT — SINGLE FILE          ║
║   1-Click Setup: python bot.py                      ║
╚══════════════════════════════════════════════════════╝

SETUP:
  1. Neeche CONFIG section mein BOT_TOKEN aur ADMIN_IDS bharo
  2. Terminal mein chalao:
       pip install python-telegram-bot qrcode pillow
       python bot.py
  3. Bot mein /start karo — ho gaya!
"""

# ================================================================
#  ██████╗ ██████╗ ███╗   ██╗███████╗██╗ ██████╗
# ██╔════╝██╔═══██╗████╗  ██║██╔════╝██║██╔════╝
# ██║     ██║   ██║██╔██╗ ██║█████╗  ██║██║  ███╗
# ██║     ██║   ██║██║╚██╗██║██╔══╝  ██║██║   ██║
# ╚██████╗╚██████╔╝██║ ╚████║██║     ██║╚██████╔╝
#  ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝ ╚═════╝
# ================================================================
#  YAHAN APNI DETAILS BHARO — SIRF YAHI EDIT KARNA HAI
# ================================================================

BOT_TOKEN     = "YAHAN_APNA_TOKEN_DAALO"      # @BotFather se milega
ADMIN_IDS     = [123456789]                    # @userinfobot se apna ID lao
ADMIN_USERNAME = "@tumhara_username"           # Admin ka Telegram username

BOT_NAME      = "🎬 My Content Bot"
FREE_MEDIA_LIMIT = 10                          # Free users ko kitni videos milein

# Plans: 7 / 15 / 30 din — price aur description change kar sakte ho
PLANS = {
    "7days": {
        "name":           "7 Days Plan",
        "duration_hours": 168,
        "price":          99,
        "description":    "🔓 Unlimited videos for 7 days"
    },
    "15days": {
        "name":           "15 Days Plan",
        "duration_hours": 360,
        "price":          149,
        "description":    "🔓 Unlimited videos for 15 days"
    },
    "30days": {
        "name":           "30 Days Plan",
        "duration_hours": 720,
        "price":          199,
        "description":    "🔓 Unlimited videos for 30 days — Best Value!"
    },
}

REFERRAL_CREDIT_TO_HOURS  = 1   # 1 credit = kitne ghante premium
REFERRAL_CREDITS_FOR_DAY  = 4   # Kitne credits = 1 din premium
DB_FILE = "bot_database.db"     # Database file naam

# ================================================================
#  WELCOME MESSAGE — {bot_name} aur {free_limit} automatically fill honge
# ================================================================
WELCOME_TEXT = """
🎉 *Welcome to {bot_name}!*

📌 Yahan aapko milega exclusive random content!

━━━━━━━━━━━━━━━━━━━━━
🆓 *Free Users:* Sirf {free_limit} videos milenge
👑 *Premium Users:* Unlimited videos!

💎 *Premium Plans:*
• 7 Days  — Unlimited Access
• 15 Days — Unlimited Access
• 30 Days — Unlimited Access
━━━━━━━━━━━━━━━━━━━━━

Neeche buttons use karein 👇
"""

# ================================================================
#  IMPORTS — inhe mat chhedo
# ================================================================
import os, sys, logging, asyncio, datetime, io, sqlite3

# Auto-install check
try:
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
    )
    from telegram.ext import (
        Application, CommandHandler, MessageHandler, CallbackQueryHandler,
        filters, ContextTypes, ConversationHandler
    )
    from telegram.error import TelegramError
    import qrcode
    from PIL import Image
except ImportError:
    print("\n📦 Libraries install ho rahi hain...\n")
    os.system(f"{sys.executable} -m pip install python-telegram-bot qrcode pillow -q")
    print("✅ Install complete! Bot restart ho raha hai...\n")
    os.execv(sys.executable, [sys.executable] + sys.argv)

logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(WAITING_SCREENSHOT, WAITING_UTR, WAITING_UPI_ID, WAITING_UPI_NAME,
 WAITING_PLAN_KEY, WAITING_PLAN_NAME, WAITING_PLAN_PRICE,
 WAITING_PLAN_DAYS, WAITING_PLAN_DESC) = range(9)

# ================================================================
#  DATABASE
# ================================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT, full_name TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        free_used INTEGER DEFAULT 0,
        referral_credits INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL,
        total_referrals INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, plan_key TEXT, plan_name TEXT, plan_days INTEGER,
        start_time TIMESTAMP, end_time TIMESTAMP,
        approved_by INTEGER, notified_expiry INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, plan_key TEXT,
        screenshot_file_id TEXT, utr_number TEXT DEFAULT NULL,
        status TEXT DEFAULT 'pending',
        requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP, reviewed_by INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT UNIQUE, file_type TEXT, caption TEXT,
        added_by INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        send_count INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS upi_settings (
        id INTEGER PRIMARY KEY,
        upi_id TEXT, upi_name TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit(); conn.close()

# ---- User ----
def db_get_user(uid):
    c = get_db(); r = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone(); c.close(); return r

def db_add_user(uid, username, full_name, referred_by=None):
    c = get_db()
    c.execute("INSERT OR IGNORE INTO users (user_id,username,full_name,referred_by) VALUES (?,?,?,?)",
              (uid, username, full_name, referred_by))
    if referred_by:
        c.execute("UPDATE users SET referral_credits=referral_credits+1, total_referrals=total_referrals+1 WHERE user_id=?",
                  (referred_by,))
    c.commit(); c.close()

def db_increment_free(uid):
    c = get_db(); c.execute("UPDATE users SET free_used=free_used+1 WHERE user_id=?", (uid,)); c.commit(); c.close()

def db_get_all_users():
    c = get_db(); r = [u["user_id"] for u in c.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()]; c.close(); return r

def db_ban(uid, val):
    c = get_db(); c.execute("UPDATE users SET is_banned=? WHERE user_id=?", (val, uid)); c.commit(); c.close()

# ---- Subscription ----
def db_is_premium(uid):
    c = get_db()
    now = datetime.datetime.now()
    r = c.execute("SELECT id FROM subscriptions WHERE user_id=? AND end_time>? LIMIT 1", (uid, now)).fetchone()
    c.close(); return r is not None

def db_get_sub_info(uid):
    c = get_db()
    now = datetime.datetime.now()
    r = c.execute("SELECT * FROM subscriptions WHERE user_id=? AND end_time>? ORDER BY end_time DESC LIMIT 1",
                  (uid, now)).fetchone()
    c.close(); return r

def db_add_subscription(uid, plan_key, hours, approved_by, plan_name=None, plan_days=None):
    c = get_db()
    now = datetime.datetime.now()
    end = now + datetime.timedelta(hours=hours)
    if plan_days is None: plan_days = round(hours / 24)
    c.execute("INSERT INTO subscriptions (user_id,plan_key,plan_name,plan_days,start_time,end_time,approved_by) VALUES (?,?,?,?,?,?,?)",
              (uid, plan_key, plan_name or plan_key, plan_days, now, end, approved_by))
    c.commit(); c.close(); return now, end

def db_get_expiring_soon(hours=24):
    c = get_db(); now = datetime.datetime.now(); soon = now + datetime.timedelta(hours=hours)
    r = c.execute("SELECT * FROM subscriptions WHERE end_time>? AND end_time<=? AND notified_expiry=0",
                  (now, soon)).fetchall(); c.close(); return r

def db_get_just_expired():
    c = get_db(); now = datetime.datetime.now(); ago = now - datetime.timedelta(minutes=10)
    r = c.execute("SELECT * FROM subscriptions WHERE end_time<=? AND end_time>? AND notified_expiry<2",
                  (now, ago)).fetchall(); c.close(); return r

def db_mark_notified(sub_id, level):
    c = get_db(); c.execute("UPDATE subscriptions SET notified_expiry=? WHERE id=?", (level, sub_id)); c.commit(); c.close()

def db_use_credits(uid, needed):
    c = get_db()
    u = c.execute("SELECT referral_credits FROM users WHERE user_id=?", (uid,)).fetchone()
    if u and u["referral_credits"] >= needed:
        c.execute("UPDATE users SET referral_credits=referral_credits-? WHERE user_id=?", (needed, uid))
        c.commit(); c.close(); return True
    c.close(); return False

# ---- Payments ----
def db_add_payment(uid, plan_key, ss_id, utr=None):
    c = get_db()
    c.execute("INSERT INTO payment_requests (user_id,plan_key,screenshot_file_id,utr_number) VALUES (?,?,?,?)",
              (uid, plan_key, ss_id, utr))
    c.commit()
    rid = c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.close(); return rid

def db_get_pending():
    c = get_db()
    r = c.execute("SELECT pr.*,u.username,u.full_name FROM payment_requests pr JOIN users u ON pr.user_id=u.user_id WHERE pr.status='pending' ORDER BY pr.requested_at ASC").fetchall()
    c.close(); return r

def db_get_payment(rid):
    c = get_db(); r = c.execute("SELECT * FROM payment_requests WHERE id=?", (rid,)).fetchone(); c.close(); return r

def db_update_payment(rid, status, by):
    c = get_db(); now = datetime.datetime.now()
    c.execute("UPDATE payment_requests SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?", (status, now, by, rid))
    c.commit(); c.close()

def db_get_expired_pending(minutes=30):
    c = get_db(); cutoff = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    r = c.execute("SELECT * FROM payment_requests WHERE status='pending' AND requested_at<?", (cutoff,)).fetchall()
    c.close(); return r

# ---- Media ----
def db_add_media(file_id, file_type, caption, added_by):
    c = get_db()
    try:
        c.execute("INSERT OR IGNORE INTO media (file_id,file_type,caption,added_by) VALUES (?,?,?,?)",
                  (file_id, file_type, caption, added_by))
        c.commit()
        ok = c.execute("SELECT changes()").fetchone()[0] > 0
    except: ok = False
    finally: c.close()
    return ok

def db_get_random_media():
    """Uploaded videos mein se koi bhi random video aaye — same bhi aa sakti hai"""
    c = get_db()
    r = c.execute("SELECT * FROM media ORDER BY RANDOM() LIMIT 1").fetchone()
    c.close(); return r

def db_media_count():
    c = get_db(); n = c.execute("SELECT COUNT(*) as c FROM media").fetchone()["c"]; c.close(); return n

def db_incr_send(mid):
    c = get_db(); c.execute("UPDATE media SET send_count=send_count+1 WHERE id=?", (mid,)); c.commit(); c.close()

def db_delete_media(mid):
    c = get_db(); c.execute("DELETE FROM media WHERE id=?", (mid,)); c.commit(); c.close()

def db_get_all_media(limit=20, offset=0):
    c = get_db(); r = c.execute("SELECT * FROM media ORDER BY added_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall(); c.close(); return r

def db_stats():
    c = get_db(); now = datetime.datetime.now(); today = datetime.date.today()
    s = {
        "total_users":      c.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"],
        "active_subs":      c.execute("SELECT COUNT(DISTINCT user_id) as c FROM subscriptions WHERE end_time>?", (now,)).fetchone()["c"],
        "pending_payments": c.execute("SELECT COUNT(*) as c FROM payment_requests WHERE status='pending'").fetchone()["c"],
        "total_media":      c.execute("SELECT COUNT(*) as c FROM media").fetchone()["c"],
        "new_today":        c.execute("SELECT COUNT(*) as c FROM users WHERE date(joined_at)=?", (today,)).fetchone()["c"],
    }
    c.close(); return s

# ---- UPI ----
def upi_save(upi_id, upi_name):
    c = get_db()
    c.execute("DELETE FROM upi_settings")
    c.execute("INSERT INTO upi_settings (id,upi_id,upi_name) VALUES (1,?,?)", (upi_id, upi_name))
    c.commit(); c.close()

def upi_get():
    c = get_db()
    try:
        r = c.execute("SELECT * FROM upi_settings WHERE id=1").fetchone()
        c.close()
        return (r["upi_id"], r["upi_name"]) if r else (None, None)
    except: c.close(); return None, None

def upi_generate_qr(upi_id, upi_name, amount, desc="Bot Subscription"):
    url = (f"upi://pay?pa={upi_id}&pn={upi_name.replace(' ','%20')}"
           f"&am={amount:.2f}&cu=INR&tn={desc.replace(' ','%20')}")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def upi_plan_qr(plan_key):
    upi_id, upi_name = upi_get()
    if not upi_id: return None
    plan = PLANS.get(plan_key)
    if not plan: return None
    buf = upi_generate_qr(upi_id, upi_name, plan["price"], f"Bot {plan['name']}")
    return buf, upi_id, upi_name, plan["price"]

# ================================================================
#  HELPERS
# ================================================================

def is_admin(uid): return uid in ADMIN_IDS

def fmt_remaining(end_str):
    try:
        diff = datetime.datetime.fromisoformat(str(end_str)) - datetime.datetime.now()
        if diff.total_seconds() <= 0: return "❌ Expired"
        s = int(diff.total_seconds())
        parts = []
        if s // 86400: parts.append(f"{s//86400} din")
        if (s % 86400) // 3600: parts.append(f"{(s%86400)//3600} ghante")
        if (s % 3600) // 60: parts.append(f"{(s%3600)//60} minute")
        return " ".join(parts) or "1 minute se kam"
    except: return "Unknown"

def fmt_dt(dt_str):
    try: return datetime.datetime.fromisoformat(str(dt_str)).strftime("%d %b %Y, %I:%M %p")
    except: return str(dt_str)

async def send_media(context, chat_id, media):
    try:
        cap = media["caption"] or ""
        kb  = get_another_kb()
        if   media["file_type"] == "photo":    await context.bot.send_photo(chat_id, photo=media["file_id"], caption=cap, reply_markup=kb)
        elif media["file_type"] == "video":    await context.bot.send_video(chat_id, video=media["file_id"], caption=cap, reply_markup=kb)
        elif media["file_type"] == "document": await context.bot.send_document(chat_id, document=media["file_id"], caption=cap, reply_markup=kb)
        db_incr_send(media["id"]); return True
    except TelegramError as e:
        logger.error(f"send_media error: {e}"); return False

# ================================================================
#  KEYBOARDS
# ================================================================

def main_kb():
    return ReplyKeyboardMarkup([
        ["🎬 Get Random Media"],
        ["💳 Subscription (/premium)", "📞 Contact Admin"],
        ["🎁 Refer & Redeem (/refer)",  "⏱ My Plan (/status)"]
    ], resize_keyboard=True)

def get_another_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Get Another", callback_data="get_another")]])

def plan_buttons_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{p['name']} — ₹{p['price']} ({p['duration_hours']//24} din)", callback_data=f"view_plan_{k}")]
        for k, p in PLANS.items()
    ])

def paid_kb(plan_key):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Maine Pay Kar Diya", callback_data=f"paid_{plan_key}")],
        [InlineKeyboardButton("🔙 Plans Dekhen",       callback_data="show_plans")]
    ])

# ================================================================
#  BACKGROUND JOBS
# ================================================================

async def job_expire_payments(context: ContextTypes.DEFAULT_TYPE):
    for req in db_get_expired_pending(minutes=30):
        try:
            db_update_payment(req["id"], "expired", 0)
            await context.bot.send_message(req["user_id"],
                "⏰ *Payment Timeout!*\n\nAapki payment 30 minute mein confirm nahi hui isliye automatically delete ho gayi.\n\nDobara pay karne ke liye /premium use karein. ✅",
                parse_mode="Markdown", reply_markup=main_kb())
        except Exception as e: logger.error(e)

async def job_expiry_check(context: ContextTypes.DEFAULT_TYPE):
    for sub in db_get_expiring_soon(hours=24):
        try:
            await context.bot.send_message(sub["user_id"],
                f"⚠️ *Plan Expire Hone Wala Hai!*\n\n📋 Plan: *{sub['plan_name']}*\n⏳ Bacha: *{fmt_remaining(sub['end_time'])}*\n📅 Expire: {fmt_dt(sub['end_time'])}\n\n🔄 Renew karne ke liye /premium use karein!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Renew Karein", callback_data="show_plans")]]))
            db_mark_notified(sub["id"], 1)
        except Exception as e: logger.error(e)

    for sub in db_get_just_expired():
        if sub["notified_expiry"] < 2:
            try:
                await context.bot.send_message(sub["user_id"],
                    f"❌ *Aapka Plan Expire Ho Gaya!*\n\n📋 Plan: *{sub['plan_name']}*\n📅 Start: {fmt_dt(sub['start_time'])}\n📅 Expire: {fmt_dt(sub['end_time'])}\n\n🔄 /premium se dobara subscribe karein!",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Dobara Subscribe Karein", callback_data="show_plans")]]))
                db_mark_notified(sub["id"], 2)
            except Exception as e: logger.error(e)

# ================================================================
#  USER HANDLERS
# ================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    if context.args:
        try:
            referred_by = int(context.args[0])
            if referred_by == user.id: referred_by = None
        except: pass

    if not db_get_user(user.id):
        db_add_user(user.id, user.username, user.full_name, referred_by)
        if referred_by:
            try: await context.bot.send_message(referred_by, f"🎉 Ek naya user aapke referral se join hua!\n👤 {user.full_name}\n💰 +1 referral credit!")
            except: pass

    await update.message.reply_text(
        WELCOME_TEXT.format(bot_name=BOT_NAME, free_limit=FREE_MEDIA_LIMIT),
        parse_mode="Markdown", reply_markup=main_kb()
    )

async def cmd_get_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = db_get_user(uid)
    if not user: await update.message.reply_text("Pehle /start karein!"); return
    if user["is_banned"]: await update.message.reply_text("❌ Aapka account ban hai."); return

    premium = db_is_premium(uid)

    # Free limit check
    if not premium and user["free_used"] >= FREE_MEDIA_LIMIT:
        await update.message.reply_text(
            f"❌ *Free Limit Khatam!*\n\n"
            f"Aapko {FREE_MEDIA_LIMIT} free videos mil chuki hain.\n\n"
            f"👑 *Premium lein aur unlimited videos enjoy karein!*\n"
            f"━━━━━━━━━━━━━━━━\n• 7 Days — Unlimited\n• 15 Days — Unlimited\n• 30 Days — Unlimited",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")]])
        ); return

    if db_media_count() == 0:
        await update.message.reply_text("⚠️ Abhi koi media nahi hai. Baad mein try karein!"); return

    media = db_get_random_media()
    if not media: await update.message.reply_text("Media nahi mila. Dobara try karein!"); return

    sent = await send_media(context, update.effective_chat.id, media)
    if sent and not premium:
        db_increment_free(uid)
        used      = user["free_used"] + 1
        remaining = FREE_MEDIA_LIMIT - used
        if remaining > 0:
            await update.message.reply_text(f"📊 Free Videos: {used}/{FREE_MEDIA_LIMIT} | ⬜ Bacha: {remaining}\n💡 Unlimited ke liye /premium lein!")
        else:
            await update.message.reply_text(
                "⚠️ *Yeh aapki aakhri free video thi!*\n\nAur videos ke liye premium lein 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")]])
            )

async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upi_id, _ = upi_get()
    if not upi_id: await update.message.reply_text("⚠️ Admin ne UPI setup nahi kiya abhi."); return
    await update.message.reply_text(
        "👑 *Premium Plans:*\n\n✅ Plan choose karein — QR milega\n✅ Pay karein → Screenshot + UTR bhejein\n✅ Admin approve karte hi *plan TURANT shuru* ho jaata hai!\n⏱ Countdown approve hone ke exact waqt se start hota hai.",
        parse_mode="Markdown", reply_markup=plan_buttons_kb()
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = db_get_user(uid)
    if not user: await update.message.reply_text("Pehle /start karein!"); return

    premium = db_is_premium(uid)
    sub     = db_get_sub_info(uid)

    if premium and sub:
        try:
            s   = datetime.datetime.fromisoformat(str(sub["start_time"]))
            e   = datetime.datetime.fromisoformat(str(sub["end_time"]))
            now = datetime.datetime.now()
            pct    = max(0, min(100, int(((now-s).total_seconds() / (e-s).total_seconds()) * 100)))
            bar    = "🟩"*(pct//10) + "⬜"*(10-pct//10)
        except: bar, pct = "⬜"*10, 0

        text = (f"👑 *Premium Active!*\n\n📋 Plan: *{sub['plan_name']}*\n"
                f"📅 Shuru: {fmt_dt(sub['start_time'])}\n📅 Khatam: {fmt_dt(sub['end_time'])}\n"
                f"⏳ Bacha: *{fmt_remaining(sub['end_time'])}*\n\n"
                f"Progress: {bar} {pct}% used\n\nReferral credits: {user['referral_credits']}")
        await update.message.reply_text(text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")]]))
    else:
        await update.message.reply_text(
            f"🆓 *Free User*\n\nFree used: {user['free_used']}/{FREE_MEDIA_LIMIT}\n"
            f"Referral credits: {user['referral_credits']}\nTotal referrals: {user['total_referrals']}\n\n"
            f"👑 Premium lene ke liye /premium use karein!",
            parse_mode="Markdown"
        )

async def cb_refresh_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer("Refreshed! ✅")
    uid   = query.from_user.id
    user  = db_get_user(uid); sub = db_get_sub_info(uid)
    if sub:
        text = (f"👑 *Premium Active!*\n\n📋 Plan: *{sub['plan_name']}*\n"
                f"📅 Shuru: {fmt_dt(sub['start_time'])}\n📅 Khatam: {fmt_dt(sub['end_time'])}\n"
                f"⏳ Bacha: *{fmt_remaining(sub['end_time'])}*\n\nReferral credits: {user['referral_credits']}")
    else:
        text = "❌ Plan expire ho gaya.\n\n/premium se renew karein!"
    try:
        await query.message.edit_text(text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")]]))
    except: pass

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = db_get_user(uid)
    if not user: await update.message.reply_text("Pehle /start karein!"); return
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={uid}"
    text = (f"🎁 *Referral Program*\n\n• 1 referral = *1 credit*\n"
            f"• 1 credit = *{REFERRAL_CREDIT_TO_HOURS} hour* premium\n"
            f"• {REFERRAL_CREDITS_FOR_DAY} credits = *1 day* premium\n\n"
            f"Stats: {user['total_referrals']} referrals | {user['referral_credits']} credits\n\n"
            f"*Referral link:*\n`{ref_link}`")
    buttons = []
    if user["referral_credits"] >= REFERRAL_CREDITS_FOR_DAY:
        buttons.append([InlineKeyboardButton(f"🎉 {REFERRAL_CREDITS_FOR_DAY} Credits = 1 Day Redeem", callback_data="redeem_day")])
    if user["referral_credits"] >= 1:
        buttons.append([InlineKeyboardButton("⏰ 1 Credit = 1 Hour Redeem", callback_data="redeem_hour")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

async def cb_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    uid   = query.from_user.id
    if query.data == "redeem_day":
        if db_use_credits(uid, REFERRAL_CREDITS_FOR_DAY):
            db_add_subscription(uid, "referral_1day", 24, 0, plan_name="Referral 1 Day", plan_days=1)
            await query.message.reply_text("🎉 1 Din ka Premium Activate!")
        else: await query.message.reply_text("❌ Enough credits nahi!")
    elif query.data == "redeem_hour":
        if db_use_credits(uid, 1):
            db_add_subscription(uid, "referral_1hour", REFERRAL_CREDIT_TO_HOURS, 0, plan_name="Referral 1 Hour", plan_days=0)
            await query.message.reply_text(f"🎉 {REFERRAL_CREDIT_TO_HOURS} Hour Premium Activate!")
        else: await query.message.reply_text("❌ Enough credits nahi!")

async def cmd_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📞 *Admin Contact:*\n\n{ADMIN_USERNAME}", parse_mode="Markdown")

# ================================================================
#  PAYMENT FLOW
# ================================================================

async def cb_show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    upi_id, _ = upi_get()
    if not upi_id: await query.message.reply_text("⚠️ UPI setup nahi hua."); return
    await query.message.reply_text("👑 *Plan Chunein:*", parse_mode="Markdown", reply_markup=plan_buttons_kb())

async def cb_view_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query; await query.answer("QR generate ho raha hai... ⏳")
    plan_key = query.data.replace("view_plan_", "")
    plan     = PLANS.get(plan_key)
    if not plan: return
    result = upi_plan_qr(plan_key)
    if not result: await query.message.reply_text("⚠️ UPI setup nahi hua!"); return
    buf, upi_id, upi_name, amount = result
    days    = plan["duration_hours"] // 24
    caption = (f"💳 *{plan['name']} — ₹{plan['price']}*\n\n⏱ Duration: *{days} din*\n📌 {plan['description']}\n\n"
               f"📲 UPI ID: `{upi_id}`\n👤 Name: {upi_name}\n💰 Amount: ₹{amount}\n\n"
               f"✅ *Pay karo → Button dabaao → Screenshot + UTR bhejo*\n⚡ Approve hote hi countdown TURANT shuru!")
    await context.bot.send_photo(query.message.chat_id, photo=buf, caption=caption, parse_mode="Markdown", reply_markup=paid_kb(plan_key))

async def cb_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query; await query.answer()
    plan_key = query.data.replace("paid_", "")
    plan     = PLANS.get(plan_key)
    if not plan: return
    context.user_data["selected_plan"] = plan_key
    days = plan["duration_hours"] // 24
    await query.message.reply_text(f"✅ Plan: *{plan['name']} — {days} Din*\n\n📸 *Step 1:* Payment screenshot bhejein.", parse_mode="Markdown")
    return WAITING_SCREENSHOT

async def recv_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_key = context.user_data.get("selected_plan")
    if not plan_key: await update.message.reply_text("Pehle /premium se plan select karein."); return ConversationHandler.END
    photo = update.message.photo; doc = update.message.document
    if photo: fid = photo[-1].file_id
    elif doc and doc.mime_type and doc.mime_type.startswith("image"): fid = doc.file_id
    else: await update.message.reply_text("❌ Sirf image bhejein!"); return WAITING_SCREENSHOT
    context.user_data["screenshot_fid"] = fid
    await update.message.reply_text("✅ Screenshot mila!\n\n🔢 *Step 2:* UTR Number bhejein.\n\nExample: `426112345678`", parse_mode="Markdown")
    return WAITING_UTR

async def recv_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    plan_key = context.user_data.get("selected_plan")
    fid      = context.user_data.get("screenshot_fid")
    utr      = update.message.text.strip()
    if not plan_key or not fid: await update.message.reply_text("❌ /premium se dobara shuru karein."); return ConversationHandler.END
    if not (6 <= len(utr) <= 25): await update.message.reply_text("❌ UTR galat hai! Dobara bhejein (6-25 characters)."); return WAITING_UTR

    rid  = db_add_payment(user.id, plan_key, fid, utr)
    plan = PLANS[plan_key]; days = plan["duration_hours"] // 24

    for aid in ADMIN_IDS:
        try:
            caption = (f"💳 *Naya Payment #{rid}*\n\n👤 {user.full_name} (@{user.username})\n🆔 `{user.id}`\n"
                       f"📋 {plan['name']} — ₹{plan['price']} ({days} din)\n🔢 UTR: `{utr}`\n⏰ {datetime.datetime.now().strftime('%d %b %Y %I:%M %p')}")
            await context.bot.send_photo(aid, photo=fid, caption=caption, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{rid}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{rid}")]]))
        except Exception as e: logger.error(e)

    await update.message.reply_text(
        f"✅ *Payment Submit Ho Gayi!*\n\n📋 Plan: {plan['name']} ({days} din)\n🔢 UTR: `{utr}`\n\n"
        f"⏳ Admin jald approve karega.\n⚡ Approve hote hi aapka *{days} din* ka plan TURANT shuru ho jaayega!\n⏰ 30 min mein confirm nahi hua toh auto-delete.",
        parse_mode="Markdown", reply_markup=main_kb()
    )
    return ConversationHandler.END

# ================================================================
#  APPROVE / REJECT
# ================================================================

async def cb_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id): await query.answer("Access denied!"); return
    rid = int(query.data.replace("approve_", ""))
    req = db_get_payment(rid)
    if not req or req["status"] != "pending": await query.answer("Already processed!"); return
    plan      = PLANS.get(req["plan_key"], {})
    hours     = plan.get("duration_hours", 24)
    plan_name = plan.get("name", req["plan_key"])
    plan_days = hours // 24
    db_update_payment(rid, "approved", query.from_user.id)
    start_time, end_time = db_add_subscription(req["user_id"], req["plan_key"], hours, query.from_user.id, plan_name=plan_name, plan_days=plan_days)
    await query.answer("✅ Approved! Countdown shuru ho gaya!")
    try: await query.message.edit_caption(query.message.caption + f"\n\n✅ *APPROVED*\n⏱ {plan_days} din ka countdown shuru!", parse_mode="Markdown")
    except: pass
    try:
        await context.bot.send_message(req["user_id"],
            f"🎉 *Subscription Approved!*\n\n📋 Plan: *{plan_name}*\n⏱ Duration: *{plan_days} din*\n\n"
            f"⏰ *Shuru:* {fmt_dt(start_time)}\n📅 *Khatam:* {fmt_dt(end_time)}\n\n"
            f"✅ Countdown ABHI se shuru ho gaya!\n📊 Status check: /status\nAb unlimited media enjoy karein! 🎬",
            parse_mode="Markdown", reply_markup=main_kb())
    except Exception as e: logger.error(e)

async def cb_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id): await query.answer("Access denied!"); return
    rid = int(query.data.replace("reject_", ""))
    req = db_get_payment(rid)
    if not req or req["status"] != "pending": await query.answer("Already processed!"); return
    db_update_payment(rid, "rejected", query.from_user.id)
    await query.answer("❌ Rejected!")
    try: await query.message.edit_caption(query.message.caption + "\n\n❌ *REJECTED*", parse_mode="Markdown")
    except: pass
    try: await context.bot.send_message(req["user_id"], f"❌ *Payment reject ho gayi.*\nAdmin se contact karein: {ADMIN_USERNAME}", parse_mode="Markdown")
    except: pass

async def cb_get_another(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    uid   = query.from_user.id
    user  = db_get_user(uid)
    if not user or user["is_banned"]: return
    premium = db_is_premium(uid)

    if not premium and user["free_used"] >= FREE_MEDIA_LIMIT:
        await query.message.reply_text(
            f"❌ *Free Limit Khatam!*\n\nAapko {FREE_MEDIA_LIMIT} free videos mil chuki hain.\n\n👑 *Premium lein aur unlimited videos enjoy karein!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")]])
        ); return

    media = db_get_random_media()
    if not media: await query.message.reply_text("Koi media nahi mila!"); return
    sent = await send_media(context, query.message.chat_id, media)
    if sent and not premium:
        db_increment_free(uid)
        used = user["free_used"] + 1
        remaining = FREE_MEDIA_LIMIT - used
        if remaining > 0:
            await query.message.reply_text(f"📊 Free Videos: {used}/{FREE_MEDIA_LIMIT} | ⬜ Bacha: {remaining}")
        else:
            await query.message.reply_text("⚠️ *Yeh aapki aakhri free video thi!*\n\nAur videos ke liye premium lein 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Premium Lein", callback_data="show_plans")]]))

# ================================================================
#  ADMIN COMMANDS
# ================================================================

async def cmd_adminown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Access denied!"); return
    await update.message.reply_text(
        "👑 *ADMIN CONTROL PANEL*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📲 *UPI & QR:*\n/setupi — UPI ID set/update karo\n/test_qr — Plans ka QR preview\n\n"
        "💰 *PLANS:*\n/changeplan — Plan price/duration change karo\n/plans_list — Saare plans dekho\n\n"
        "🎬 *MEDIA:*\n/add_media — Media add karo\n/done — Adding band karo\n"
        "/media_list — Media list\n/del_media [id] — Delete karo\n\n"
        "💳 *PAYMENTS:*\n/pending — Pending payments\n/give_premium [id] [days] — Manual premium do\n\n"
        "👥 *USERS:*\n/ban [id] — Ban karo\n/unban [id] — Unban karo\n/broadcast — Sab ko message\n\n"
        "📊 *STATS:* /admin\n━━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ Payment timeout: 30 min\n🔔 Expiry warning: 24 ghante pehle\n✅ Countdown: Approve ke exact second se",
        parse_mode="Markdown"
    )

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Access denied!"); return
    s  = db_stats(); upi_id, upi_name = upi_get()
    us = f"✅ `{upi_id}` ({upi_name})" if upi_id else "❌ Set nahi hua"
    await update.message.reply_text(
        f"🔧 *Admin Panel*\n\n👥 Total Users: {s['total_users']}\n🆕 New Today: {s['new_today']}\n"
        f"👑 Active Subs: {s['active_subs']}\n🎬 Total Media: {s['total_media']}\n💳 Pending: {s['pending_payments']}\n\n"
        f"UPI: {us}\n\nSaare commands: /adminown",
        parse_mode="Markdown"
    )

async def cmd_setupi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    upi_id, upi_name = upi_get()
    cur = f"\n\nCurrent: `{upi_id}` ({upi_name})" if upi_id else ""
    await update.message.reply_text(f"💳 *UPI Setup*{cur}\n\nUPI ID bhejein:", parse_mode="Markdown")
    return WAITING_UPI_ID

async def recv_upi_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    uid_val = update.message.text.strip()
    if "@" not in uid_val: await update.message.reply_text("❌ Sahi UPI ID dein (example: name@paytm)"); return WAITING_UPI_ID
    context.user_data["new_upi_id"] = uid_val
    await update.message.reply_text(f"✅ `{uid_val}`\n\nAb naam bhejein:", parse_mode="Markdown")
    return WAITING_UPI_NAME

async def recv_upi_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    upi_name_val = update.message.text.strip()
    upi_id_val   = context.user_data.get("new_upi_id")
    upi_save(upi_id_val, upi_name_val)
    buf = upi_generate_qr(upi_id_val, upi_name_val, 10.0, "Test QR")
    await context.bot.send_photo(update.effective_chat.id, photo=buf,
        caption=f"✅ *UPI Set!*\nID: `{upi_id_val}`\nName: {upi_name_val}", parse_mode="Markdown")
    return ConversationHandler.END

async def cmd_test_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    upi_id, upi_name = upi_get()
    if not upi_id: await update.message.reply_text("❌ Pehle /setupi se UPI set karein!"); return
    for key, plan in PLANS.items():
        buf = upi_generate_qr(upi_id, upi_name, plan["price"], f"Bot {plan['name']}")
        await context.bot.send_photo(update.effective_chat.id, photo=buf,
            caption=f"*{plan['name']} — ₹{plan['price']} ({plan['duration_hours']//24} din)*\nUPI: `{upi_id}`", parse_mode="Markdown")

async def cmd_plans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    text = "📋 *Current Plans:*\n\n"
    for k, p in PLANS.items():
        text += f"🔑 `{k}` — {p['name']}\n💰 ₹{p['price']} | ⏱ {p['duration_hours']//24} din\n📝 {p['description']}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_changeplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    keys = "\n".join([f"• `{k}` — {v['name']} (₹{v['price']}, {v['duration_hours']//24} din)" for k, v in PLANS.items()])
    await update.message.reply_text(f"💰 *Plan Change*\n\n{keys}\n\nPlan key bhejein:", parse_mode="Markdown")
    return WAITING_PLAN_KEY

async def recv_plan_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    key = update.message.text.strip()
    if key not in PLANS: await update.message.reply_text("❌ Sahi key bhejein."); return WAITING_PLAN_KEY
    context.user_data["edit_plan_key"] = key
    await update.message.reply_text(f"Plan: *{PLANS[key]['name']}*\nNaya naam bhejein (/skip same rakhne ke liye):", parse_mode="Markdown")
    return WAITING_PLAN_NAME

async def recv_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    key = context.user_data.get("edit_plan_key"); val = update.message.text.strip()
    if val != "/skip": PLANS[key]["name"] = val
    await update.message.reply_text(f"Naya price bhejein (current: ₹{PLANS[key]['price']}):")
    return WAITING_PLAN_PRICE

async def recv_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    key = context.user_data.get("edit_plan_key"); val = update.message.text.strip()
    if val != "/skip":
        try: PLANS[key]["price"] = int(val)
        except: await update.message.reply_text("❌ Sirf number dein!"); return WAITING_PLAN_PRICE
    await update.message.reply_text(f"⏱ Duration (days) bhejein (current: {PLANS[key]['duration_hours']//24} din):")
    return WAITING_PLAN_DAYS

async def recv_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    key = context.user_data.get("edit_plan_key"); val = update.message.text.strip()
    if val != "/skip":
        try: PLANS[key]["duration_hours"] = int(val) * 24
        except: await update.message.reply_text("❌ Sirf days number dein!"); return WAITING_PLAN_DAYS
    await update.message.reply_text("📝 Description bhejein (/skip same rakhne ke liye):")
    return WAITING_PLAN_DESC

async def recv_plan_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    key = context.user_data.get("edit_plan_key"); val = update.message.text.strip()
    if val != "/skip": PLANS[key]["description"] = val
    p = PLANS[key]
    await update.message.reply_text(
        f"✅ *Plan Updated!*\n\n`{key}` — {p['name']}\n💰 ₹{p['price']} | ⏱ {p['duration_hours']//24} din\n📝 {p['description']}\n\n⚠️ Permanent change ke liye bot.py ka CONFIG section update karein.",
        parse_mode="Markdown")
    return ConversationHandler.END

async def cmd_add_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data["adding_media"] = True
    await update.message.reply_text(f"📤 Photo/Video bhejein. /done karo jab complete ho.\n\nTotal abhi: {db_media_count()}")

async def recv_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.user_data.get("adding_media"): return
    caption = update.message.caption or ""
    if   update.message.photo:    fid, ftype = update.message.photo[-1].file_id, "photo"
    elif update.message.video:    fid, ftype = update.message.video.file_id,    "video"
    elif update.message.document: fid, ftype = update.message.document.file_id, "document"
    else: return
    ok = db_add_media(fid, ftype, caption, update.effective_user.id)
    await update.message.reply_text(f"{'✅ Added!' if ok else '⚠️ Already exists!'} Total: {db_media_count()}")

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data["adding_media"] = False
    await update.message.reply_text(f"✅ Done! Total media: {db_media_count()}")

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    reqs = db_get_pending()
    if not reqs: await update.message.reply_text("✅ Koi pending payment nahi!"); return
    await update.message.reply_text(f"📋 {len(reqs)} pending:")
    for req in reqs:
        plan = PLANS.get(req["plan_key"], {}); days = plan.get("duration_hours", 24) // 24
        utr_info = f"\n🔢 UTR: `{req['utr_number']}`" if req["utr_number"] else "\n⚠️ UTR: N/A"
        caption  = (f"💳 *#{req['id']}*\n👤 {req['full_name']} (@{req['username']})\n🆔 `{req['user_id']}`\n"
                    f"📋 {plan.get('name','?')} — ₹{plan.get('price','?')} ({days} din){utr_info}\n⏰ {req['requested_at']}")
        try:
            await context.bot.send_photo(update.effective_chat.id, photo=req["screenshot_file_id"], caption=caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{req['id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{req['id']}")]])
            )
        except: await update.message.reply_text(caption, parse_mode="Markdown")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data["broadcasting"] = True
    await update.message.reply_text("📢 Message bhejein (text/photo/video):")

async def recv_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.user_data.get("broadcasting"): return
    context.user_data["broadcasting"] = False
    all_users = db_get_all_users()
    ok = fail = 0
    await update.message.reply_text(f"📢 {len(all_users)} users ko bhej raha hoon...")
    for uid in all_users:
        try: await update.message.copy(chat_id=uid); ok += 1; await asyncio.sleep(0.05)
        except: fail += 1
    await update.message.reply_text(f"✅ Done!\n✅ {ok} success\n❌ {fail} failed")

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: await update.message.reply_text("Usage: /ban [user_id]"); return
    try:
        t = int(context.args[0]); db_ban(t, 1)
        await update.message.reply_text(f"✅ {t} banned!")
        await context.bot.send_message(t, "❌ Aapka account ban ho gaya!")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: await update.message.reply_text("Usage: /unban [user_id]"); return
    try:
        t = int(context.args[0]); db_ban(t, 0)
        await update.message.reply_text(f"✅ {t} unbanned!")
        await context.bot.send_message(t, "✅ Account unban! /start karein.")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def cmd_give_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) < 2: await update.message.reply_text("Usage: /give_premium [user_id] [days]"); return
    try:
        t = int(context.args[0]); days = int(context.args[1])
        s, e = db_add_subscription(t, f"manual_{days}day", days*24, update.effective_user.id, plan_name=f"Admin Gift {days} Din", plan_days=days)
        await update.message.reply_text(f"✅ {t} ko {days} din ka premium diya!\n⏰ Shuru: {fmt_dt(s)}\n📅 Khatam: {fmt_dt(e)}")
        await context.bot.send_message(t,
            f"🎉 Admin ne aapko *{days} din* ka FREE Premium diya!\n\n⏰ Shuru: {fmt_dt(s)}\n📅 Khatam: {fmt_dt(e)}\n\nEnjoy karein! 🎬",
            parse_mode="Markdown", reply_markup=main_kb())
    except Exception as e: await update.message.reply_text(f"Error: {e}")

async def cmd_media_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    total = db_media_count(); media_list = db_get_all_media(20)
    if not media_list: await update.message.reply_text("Koi media nahi!"); return
    text = f"🎬 *Media* (Total: {total})\n\n"
    for m in media_list: text += f"ID:{m['id']} | {m['file_type']} | Sent:{m['send_count']}x\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_del_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: await update.message.reply_text("Usage: /del_media [id]"); return
    try: db_delete_media(int(context.args[0])); await update.message.reply_text("✅ Deleted!")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

# ================================================================
#  BUTTON HANDLER
# ================================================================

async def btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if   text == "🎬 Get Random Media":              await cmd_get_media(update, context)
    elif text == "💳 Subscription (/premium)":       await cmd_premium(update, context)
    elif text == "📞 Contact Admin":                  await cmd_contact(update, context)
    elif text == "🎁 Refer & Redeem (/refer)":       await cmd_refer(update, context)
    elif text == "⏱ My Plan (/status)":              await cmd_status(update, context)
    elif is_admin(update.effective_user.id) and context.user_data.get("broadcasting"):
        await recv_broadcast(update, context)

# ================================================================
#  MAIN — BOT START
# ================================================================

def main():
    # Token check
    if BOT_TOKEN == "YAHAN_APNA_TOKEN_DAALO":
        print("\n" + "="*55)
        print("  ❌  BOT_TOKEN set nahi hai!")
        print("  bot.py kholo aur CONFIG section mein:")
        print("  BOT_TOKEN = 'apna token yahan daalo'")
        print("  ADMIN_IDS = [apna user id]")
        print("="*55 + "\n")
        sys.exit(1)

    print("\n" + "="*55)
    print(f"  🚀  {BOT_NAME} start ho raha hai...")
    print("="*55)

    init_db()
    print("✅ Database ready")

    app = Application.builder().token(BOT_TOKEN).build()

    # Background jobs
    app.job_queue.run_repeating(job_expire_payments, interval=300,  first=60)
    app.job_queue.run_repeating(job_expiry_check,    interval=1800, first=120)

    # Conversations
    upi_conv = ConversationHandler(
        entry_points=[CommandHandler("setupi", cmd_setupi)],
        states={WAITING_UPI_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_upi_id)],
                WAITING_UPI_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_upi_name)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    plan_conv = ConversationHandler(
        entry_points=[CommandHandler("changeplan", cmd_changeplan)],
        states={WAITING_PLAN_KEY:   [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_plan_key)],
                WAITING_PLAN_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_plan_name)],
                WAITING_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_plan_price)],
                WAITING_PLAN_DAYS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_plan_days)],
                WAITING_PLAN_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_plan_desc)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    pay_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_paid, pattern=r"^paid_")],
        states={WAITING_SCREENSHOT: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, recv_screenshot)],
                WAITING_UTR:        [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_utr)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    # User commands
    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("premium",       cmd_premium))
    app.add_handler(CommandHandler("refer",         cmd_refer))
    app.add_handler(CommandHandler("status",        cmd_status))
    app.add_handler(CommandHandler("contact_admin", cmd_contact))

    # Admin commands
    app.add_handler(CommandHandler("adminown",      cmd_adminown))
    app.add_handler(CommandHandler("admin",         cmd_admin))
    app.add_handler(CommandHandler("add_media",     cmd_add_media))
    app.add_handler(CommandHandler("done",          cmd_done))
    app.add_handler(CommandHandler("pending",       cmd_pending))
    app.add_handler(CommandHandler("broadcast",     cmd_broadcast))
    app.add_handler(CommandHandler("ban",           cmd_ban))
    app.add_handler(CommandHandler("unban",         cmd_unban))
    app.add_handler(CommandHandler("give_premium",  cmd_give_premium))
    app.add_handler(CommandHandler("media_list",    cmd_media_list))
    app.add_handler(CommandHandler("del_media",     cmd_del_media))
    app.add_handler(CommandHandler("test_qr",       cmd_test_qr))
    app.add_handler(CommandHandler("plans_list",    cmd_plans_list))

    # Conversations
    app.add_handler(upi_conv)
    app.add_handler(plan_conv)
    app.add_handler(pay_conv)

    # Callbacks
    app.add_handler(CallbackQueryHandler(cb_show_plans,     pattern="^show_plans$"))
    app.add_handler(CallbackQueryHandler(cb_view_plan,      pattern=r"^view_plan_"))
    app.add_handler(CallbackQueryHandler(cb_get_another,    pattern="^get_another$"))
    app.add_handler(CallbackQueryHandler(cb_approve,        pattern=r"^approve_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_reject,         pattern=r"^reject_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_redeem,         pattern=r"^redeem_"))
    app.add_handler(CallbackQueryHandler(cb_refresh_status, pattern="^refresh_status$"))

    # Admin media upload
    app.add_handler(MessageHandler(
        filters.User(ADMIN_IDS) & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        recv_admin_media
    ))

    # Text buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, btn_handler))

    print(f"✅ Bot ready! @{BOT_NAME}")
    print("📌 Bot mein jaao aur /start karo\n")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
