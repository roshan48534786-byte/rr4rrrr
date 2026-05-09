# ============================================
#  BOT CONFIGURATION
# ============================================

BOT_TOKEN = "8610399152:AAFPmvKOuXZxu8m9mcbbCUmYfSYsN8YYAuc"
ADMIN_IDS = [6732862108]
ADMIN_USERNAME = "@admin"

# Bot Name & Welcome
BOT_NAME = "🎬 My Content Bot"
WELCOME_TEXT = """
🎉 *Welcome to {bot_name}!*

📌 Yahan aapko milega exclusive random content!

━━━━━━━━━━━━━━━━━━━━━
🆓 *Free Users:* Sirf {free_limit} videos milenge
👑 *Premium Users:* Unlimited videos!

💎 *Premium Plans:*
• 7 Days — Unlimited Access
• 15 Days — Unlimited Access  
• 30 Days — Unlimited Access
━━━━━━━━━━━━━━━━━━━━━

Neeche buttons use karein 👇
"""

# Free Media Limit (non-premium users)
FREE_MEDIA_LIMIT = 10

# Subscription Plans — 7 / 15 / 30 days
PLANS = {
    "7days": {
        "name": "7 Days Plan",
        "duration_hours": 168,
        "price": 99,
        "description": "🔓 Unlimited videos for 7 days"
    },
    "15days": {
        "name": "15 Days Plan",
        "duration_hours": 360,
        "price": 149,
        "description": "🔓 Unlimited videos for 15 days"
    },
    "30days": {
        "name": "30 Days Plan",
        "duration_hours": 720,
        "price": 199,
        "description": "🔓 Unlimited videos for 30 days — Best Value!"
    }
}

# Referral System
REFERRAL_CREDIT_PER_REFER = 1
REFERRAL_CREDIT_TO_HOURS = 1
REFERRAL_CREDITS_FOR_DAY = 4

# Database
DB_FILE = "bot_database.db"
