"""
UPI QR Code Generator
Admin /setupi command se UPI set karta hai
Har plan ke liye automatic QR generate hota hai
"""

import qrcode
import io
import sqlite3
from config import DB_FILE

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_upi_table():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS upi_settings (
        id INTEGER PRIMARY KEY,
        upi_id TEXT,
        upi_name TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def save_upi(upi_id: str, upi_name: str):
    conn = get_db()
    conn.execute("DELETE FROM upi_settings")
    conn.execute("INSERT INTO upi_settings (id, upi_id, upi_name) VALUES (1, ?, ?)", (upi_id, upi_name))
    conn.commit()
    conn.close()

def get_upi():
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM upi_settings WHERE id=1").fetchone()
        conn.close()
        if row:
            return row['upi_id'], row['upi_name']
    except:
        conn.close()
    return None, None

def generate_upi_qr(upi_id: str, upi_name: str, amount: float, description: str = "Bot Subscription") -> io.BytesIO:
    """
    UPI deep link format se QR generate karta hai.
    Scan karne par amount auto-fill ho jaata hai.
    """
    upi_url = (
        f"upi://pay?"
        f"pa={upi_id}"
        f"&pn={upi_name.replace(' ', '%20')}"
        f"&am={amount:.2f}"
        f"&cu=INR"
        f"&tn={description.replace(' ', '%20')}"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(upi_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1a1a2e", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def get_plan_qr(plan_key: str, plans: dict) -> tuple:
    """
    Plan ke liye QR return karta hai.
    Returns: (BytesIO image, upi_id, upi_name, amount) or None
    """
    upi_id, upi_name = get_upi()
    if not upi_id:
        return None

    plan = plans.get(plan_key)
    if not plan:
        return None

    amount = plan['price']
    description = f"Bot {plan['name']}"
    qr_buf = generate_upi_qr(upi_id, upi_name, amount, description)
    return qr_buf, upi_id, upi_name, amount
