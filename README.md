# 🤖 Telegram Bot — Setup Guide

## 📁 Files
- `bot.py` — Main bot code
- `database.py` — Database functions
- `config.py` — All settings (aap yahan changes karein)
- `requirements.txt` — Dependencies

---

## ⚙️ Setup Steps

### Step 1: Bot Token lein
1. Telegram pe @BotFather ko open karein
2. `/newbot` command bhejein
3. Bot ka naam aur username dein
4. Token copy karein

### Step 2: Apna User ID lein
1. @userinfobot ko message karein
2. Aapka User ID milega (numbers mein)

### Step 3: config.py edit karein
```python
BOT_TOKEN = "1234567890:ABCdefGHI..."    # Apna token
ADMIN_IDS = [987654321]                   # Apna User ID
ADMIN_USERNAME = "@apna_username"
UPI_ID = "yourname@paytm"
UPI_NAME = "Apna Naam"
```

### Step 4: UPI QR Image
- Apne UPI ka QR code screenshot lein
- `upi_qr.jpg` naam se save karein
- Bot folder mein rakhein

### Step 5: Install & Run
```bash
pip install -r requirements.txt
python bot.py
```

---

## 🎬 Media Add Karna (Admin)
1. Bot ko `/add_media` bhejein
2. Photos/Videos bhejein (multiple ek sath)
3. `/done` karein jab finish ho

---

## 👑 Admin Commands

| Command | Kaam |
|---------|------|
| `/admin` | Admin panel + stats |
| `/add_media` | Naya media add karein |
| `/pending` | Pending payments dekhen |
| `/broadcast` | Sab ko message |
| `/ban [user_id]` | User ban karein |
| `/unban [user_id]` | User unban karein |
| `/give_premium [user_id] [days]` | Manual premium dein |
| `/media_list` | Saari media list |
| `/del_media [id]` | Media delete karein |

---

## 👤 User Features

| Feature | Details |
|---------|---------|
| Free Media | 10 free media milte hain |
| Random Media | Button se random content milega |
| Subscription | UPI se payment, screenshot bhejein |
| Admin Approval | Admin approve karega |
| Referral | 1 refer = 1 credit = 1 hour premium |
| Status | `/status` se apna account dekhen |

---

## 💳 Subscription Plans (config.py mein change karein)
- **1 Day** — ₹49
- **7 Days** — ₹99
- **30 Days** — ₹150

---

## 🔄 Payment Flow
1. User → Premium button dabata hai
2. UPI QR dikhta hai
3. User pay karta hai
4. "I have paid" dabata hai
5. Plan select karta hai
6. Screenshot bhejta hai
7. **Admin ko notification aata hai**
8. Admin Approve/Reject karta hai
9. User ko automatic message aata hai

---

## 🚀 Server pe Run Karna (24/7)
```bash
# Background mein run karein
nohup python bot.py &

# Ya screen use karein
screen -S mybot
python bot.py
# Ctrl+A then D to detach
```

### Free Hosting Options:
- **Railway.app** (recommended, free)
- **Render.com** (free tier)
- **Oracle Cloud** (always free)
