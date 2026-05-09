import sqlite3
import datetime
from config import DB_FILE

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        free_used INTEGER DEFAULT 0,
        referral_credits INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL,
        total_referrals INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0
    )''')

    # Subscriptions — exact start/end time ke saath
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan_key TEXT,
        plan_name TEXT,
        plan_days INTEGER,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        approved_by INTEGER,
        notified_expiry INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Payment requests — UTR support ke saath
    c.execute('''CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan_key TEXT,
        screenshot_file_id TEXT,
        utr_number TEXT DEFAULT NULL,
        status TEXT DEFAULT 'pending',
        requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP,
        reviewed_by INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT UNIQUE,
        file_type TEXT,
        caption TEXT,
        added_by INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        send_count INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT,
        sent_by INTEGER,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0
    )''')

    conn.commit()
    conn.close()

# ---- USER FUNCTIONS ----

def get_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return user

def add_user(user_id, username, full_name, referred_by=None):
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, referred_by) VALUES (?,?,?,?)",
            (user_id, username, full_name, referred_by)
        )
        if referred_by:
            conn.execute(
                "UPDATE users SET referral_credits = referral_credits + 1, total_referrals = total_referrals + 1 WHERE user_id=?",
                (referred_by,)
            )
        conn.commit()
    finally:
        conn.close()

def increment_free_used(user_id):
    conn = get_db()
    conn.execute("UPDATE users SET free_used = free_used + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
    conn.close()
    return [u['user_id'] for u in users]

def ban_user(user_id):
    conn = get_db()
    conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = get_db()
    conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# ---- SUBSCRIPTION FUNCTIONS ----

def is_premium(user_id):
    conn = get_db()
    now = datetime.datetime.now()
    sub = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? AND end_time > ? ORDER BY end_time DESC LIMIT 1",
        (user_id, now)
    ).fetchone()
    conn.close()
    return sub is not None

def get_subscription_info(user_id):
    """Active subscription ki full details — time remaining ke saath"""
    conn = get_db()
    now = datetime.datetime.now()
    sub = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? AND end_time > ? ORDER BY end_time DESC LIMIT 1",
        (user_id, now)
    ).fetchone()
    conn.close()
    return sub

def get_all_active_subscriptions():
    """Saari active subscriptions — expiry check ke liye"""
    conn = get_db()
    now = datetime.datetime.now()
    subs = conn.execute(
        "SELECT * FROM subscriptions WHERE end_time > ?", (now,)
    ).fetchall()
    conn.close()
    return subs

def get_subscriptions_expiring_soon(hours=24):
    """Jo subscriptions X hours mein expire hone wali hain"""
    conn = get_db()
    now = datetime.datetime.now()
    soon = now + datetime.timedelta(hours=hours)
    subs = conn.execute(
        "SELECT * FROM subscriptions WHERE end_time > ? AND end_time <= ? AND notified_expiry=0",
        (now, soon)
    ).fetchall()
    conn.close()
    return subs

def get_just_expired_subscriptions():
    """Jo abhi-abhi expire hui hain (last 10 min mein)"""
    conn = get_db()
    now = datetime.datetime.now()
    ten_min_ago = now - datetime.timedelta(minutes=10)
    subs = conn.execute(
        "SELECT * FROM subscriptions WHERE end_time <= ? AND end_time > ? AND notified_expiry < 2",
        (now, ten_min_ago)
    ).fetchall()
    conn.close()
    return subs

def mark_expiry_notified(sub_id, level=1):
    """1 = warning bhej di, 2 = expired notification bhej di"""
    conn = get_db()
    conn.execute("UPDATE subscriptions SET notified_expiry=? WHERE id=?", (level, sub_id))
    conn.commit()
    conn.close()

def add_subscription(user_id, plan_key, hours, approved_by, plan_name=None, plan_days=None):
    """
    Plan approve hote hi exact time se countdown start.
    hours = plan ki total duration
    """
    conn = get_db()
    now = datetime.datetime.now()
    end = now + datetime.timedelta(hours=hours)

    # Plan days calculate karo agar nahi diya
    if plan_days is None:
        plan_days = round(hours / 24)

    conn.execute(
        """INSERT INTO subscriptions 
           (user_id, plan_key, plan_name, plan_days, start_time, end_time, approved_by) 
           VALUES (?,?,?,?,?,?,?)""",
        (user_id, plan_key, plan_name or plan_key, plan_days, now, end, approved_by)
    )
    conn.commit()
    conn.close()
    return now, end

def use_referral_credits(user_id, credits_needed):
    conn = get_db()
    user = conn.execute("SELECT referral_credits FROM users WHERE user_id=?", (user_id,)).fetchone()
    if user and user['referral_credits'] >= credits_needed:
        conn.execute(
            "UPDATE users SET referral_credits = referral_credits - ? WHERE user_id=?",
            (credits_needed, user_id)
        )
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# ---- PAYMENT FUNCTIONS ----

def add_payment_request(user_id, plan_key, screenshot_file_id, utr_number=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO payment_requests (user_id, plan_key, screenshot_file_id, utr_number) VALUES (?,?,?,?)",
        (user_id, plan_key, screenshot_file_id, utr_number)
    )
    conn.commit()
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return req_id

def get_pending_payments():
    conn = get_db()
    reqs = conn.execute(
        "SELECT pr.*, u.username, u.full_name FROM payment_requests pr JOIN users u ON pr.user_id=u.user_id WHERE pr.status='pending' ORDER BY pr.requested_at ASC"
    ).fetchall()
    conn.close()
    return reqs

def get_payment_request(req_id):
    conn = get_db()
    req = conn.execute("SELECT * FROM payment_requests WHERE id=?", (req_id,)).fetchone()
    conn.close()
    return req

def update_payment_status(req_id, status, reviewed_by):
    conn = get_db()
    now = datetime.datetime.now()
    conn.execute(
        "UPDATE payment_requests SET status=?, reviewed_at=?, reviewed_by=? WHERE id=?",
        (status, now, reviewed_by, req_id)
    )
    conn.commit()
    conn.close()

def get_expired_pending_payments(minutes=30):
    conn = get_db()
    cutoff = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    reqs = conn.execute(
        "SELECT * FROM payment_requests WHERE status='pending' AND requested_at < ?",
        (cutoff,)
    ).fetchall()
    conn.close()
    return reqs

def delete_payment_request(req_id):
    conn = get_db()
    conn.execute("DELETE FROM payment_requests WHERE id=?", (req_id,))
    conn.commit()
    conn.close()

# ---- MEDIA FUNCTIONS ----

def add_media(file_id, file_type, caption, added_by):
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO media (file_id, file_type, caption, added_by) VALUES (?,?,?,?)",
            (file_id, file_type, caption, added_by)
        )
        conn.commit()
        success = conn.execute("SELECT changes()").fetchone()[0] > 0
    except:
        success = False
    finally:
        conn.close()
    return success

def get_random_media(exclude_ids=None):
    """
    Uploaded videos mein se RANDOM ek video return karo.
    Same video baar baar aa sakti hai — yahi behavior chahiye.
    """
    conn = get_db()
    if exclude_ids:
        placeholders = ','.join(['?'] * len(exclude_ids))
        media = conn.execute(
            f"SELECT * FROM media WHERE id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT 1",
            exclude_ids
        ).fetchone()
        # Agar sab exclude ho gaye toh sab mein se random do
        if not media:
            media = conn.execute("SELECT * FROM media ORDER BY RANDOM() LIMIT 1").fetchone()
    else:
        media = conn.execute("SELECT * FROM media ORDER BY RANDOM() LIMIT 1").fetchone()
    conn.close()
    return media

def increment_send_count(media_id):
    conn = get_db()
    conn.execute("UPDATE media SET send_count = send_count + 1 WHERE id=?", (media_id,))
    conn.commit()
    conn.close()

def get_media_count():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM media").fetchone()['c']
    conn.close()
    return count

def delete_media(media_id):
    conn = get_db()
    conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    conn.commit()
    conn.close()

def get_all_media(limit=20, offset=0):
    conn = get_db()
    media = conn.execute("SELECT * FROM media ORDER BY added_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    conn.close()
    return media

# ---- STATS ----

def get_stats():
    conn = get_db()
    now = datetime.datetime.now()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    active_subs = conn.execute(
        "SELECT COUNT(DISTINCT user_id) as c FROM subscriptions WHERE end_time > ?", (now,)
    ).fetchone()['c']
    pending_payments = conn.execute(
        "SELECT COUNT(*) as c FROM payment_requests WHERE status='pending'"
    ).fetchone()['c']
    total_media = conn.execute("SELECT COUNT(*) as c FROM media").fetchone()['c']
    today = datetime.date.today()
    new_today = conn.execute(
        "SELECT COUNT(*) as c FROM users WHERE date(joined_at)=?", (today,)
    ).fetchone()['c']
    conn.close()
    return {
        'total_users': total_users,
        'active_subs': active_subs,
        'pending_payments': pending_payments,
        'total_media': total_media,
        'new_today': new_today
    }
