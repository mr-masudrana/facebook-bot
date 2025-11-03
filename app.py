import re
import requests
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ==============================
# 🔧 Load Environment Variables
# ==============================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FB_APP_ID = os.getenv("FB_APP_ID", "")
FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")

# ==============================
# 🔍 Extract ID or username
# ==============================
FB_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?facebook\.com/(?:profile\.php\?id=(?P<id>\d+)|(?P<username>[^/?&#]+))",
    re.IGNORECASE
)

def extract_fb_id_or_username(url: str):
    m = FB_URL_RE.search(url.strip())
    if not m:
        return None, None
    return (m.group("id"), m.group("username"))


# ==============================
# 🔐 Facebook App Token
# ==============================
def get_fb_app_token():
    if FB_APP_ID and FB_APP_SECRET:
        return f"{FB_APP_ID}|{FB_APP_SECRET}"
    return None


# ==============================
# 🧠 Fetch Profile via Graph API
# ==============================
def fetch_profile_data_graph(identifier: str):
    app_token = get_fb_app_token()
    params = {"fields": "name,username,id,picture.type(large)"}
    if app_token:
        params["access_token"] = app_token

    url = f"https://graph.facebook.com/{identifier}"
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if "error" in data:
            return {"success": False, "error": data["error"]["message"]}

        img_url = data.get("picture", {}).get("data", {}).get("url")
        if not img_url:
            return {"success": False, "error": "No profile picture found"}

        img_resp = requests.get(img_url, timeout=10)
        img_resp.raise_for_status()

        return {
            "success": True,
            "name": data.get("name", "Unknown"),
            "username": data.get("username"),
            "id": data.get("id"),
            "image_bytes": img_resp.content,
            "image_url": img_url
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==============================
# 🌐 HTML fallback (og:image, og:title)
# ==============================
def fetch_profile_data_html(profile_url: str, identifier: str, is_id: bool):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(profile_url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {"success": False, "error": f"HTTP {r.status_code}"}

        soup = BeautifulSoup(r.text, "html.parser")
        meta_img = soup.find("meta", property="og:image")
        meta_title = soup.find("meta", property="og:title")

        img_url = meta_img["content"] if meta_img else None
        name = meta_title["content"] if meta_title else "Unknown Name"

        if not img_url:
            return {"success": False, "error": "No og:image found"}

        img_resp = requests.get(img_url, headers=headers, timeout=10)
        img_resp.raise_for_status()

        return {
            "success": True,
            "name": name,
            "username": None if is_id else identifier,
            "id": identifier if is_id else None,
            "image_bytes": img_resp.content,
            "image_url": img_url
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==============================
# 🤖 Telegram Handlers
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 হ্যালো! আমাকে ফেসবুক প্রোফাইল লিংক দিন — আমি নাম, ইউজারনেম/আইডি ও প্রোফাইল ছবি দেখাবো।\n\n"
        "উদাহরণ:\n👉 https://facebook.com/zuck\nঅথবা\n👉 https://facebook.com/profile.php?id=123456789"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    fb_id, username = extract_fb_id_or_username(text)

    if not fb_id and not username:
        await update.message.reply_text("❌ দয়া করে একটি সঠিক Facebook প্রোফাইল লিংক দিন।")
        return

    identifier = username or fb_id
    profile_url = f"https://facebook.com/{identifier}"
    await update.message.reply_text("🔎 প্রোফাইল তথ্য খোঁজা হচ্ছে...")

    # 1️⃣ Graph API দিয়ে চেষ্টা
    result = fetch_profile_data_graph(identifier)
    if not result["success"]:
        # 2️⃣ HTML fallback
        result = fetch_profile_data_html(profile_url, identifier, is_id=bool(fb_id))

    if not result["success"]:
        await update.message.reply_text("😔 তথ্য আনা যায়নি। কারণ: " + result.get("error", "অজানা সমস্যা"))
        return

    # ✅ Inline Buttons: 2টি পাশাপাশি
    keyboard = [
        [
            InlineKeyboardButton("🔗 View Full Picture", url=result["image_url"]),
            InlineKeyboardButton("🌐 Go to Facebook", url=profile_url)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ✅ Caption তৈরি করা
    caption = f"🧑‍💼 নাম: {result['name']}\n"
    if result["username"]:
        caption += f"🔖 Username: {result['username']}"
    elif result["id"]:
        caption += f"🆔 ID: {result['id']}"

    await update.message.reply_photo(photo=result["image_bytes"], caption=caption, reply_markup=reply_markup)


# ==============================
# 🚀 Main Function
# ==============================
def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN সেট করা নেই! .env ফাইল চেক করুন।")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()