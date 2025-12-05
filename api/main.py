import os
import re
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# 🔧 Load environment
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FB_APP_ID = os.getenv("FB_APP_ID", "")
FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")

# ----------------------------- #
#  Facebook Helper Functions
# ----------------------------- #
FB_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?facebook\.com/(?:profile\.php\?id=(?P<id>\d+)|(?P<username>[^/?&#]+))",
    re.IGNORECASE
)

def extract_fb_id_or_username(url: str):
    m = FB_URL_RE.search(url.strip())
    if not m:
        return None, None
    return (m.group("id"), m.group("username"))

def get_fb_app_token():
    if FB_APP_ID and FB_APP_SECRET:
        return f"{FB_APP_ID}|{FB_APP_SECRET}"
    return None

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
        name = meta_title["content"] if meta_title else "Unknown"
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

# ----------------------------- #
#  Telegram Bot Handlers
# ----------------------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 আমাকে ফেসবুক প্রোফাইল লিংক দিন, আমি নাম, ইউজারনেম/আইডি ও প্রোফাইল ছবি দেখাবো।\n\n"
        "উদাহরণ:\n👉 https://facebook.com/zuck\nঅথবা\n👉 https://facebook.com/profile.php?id=123456789"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    fb_id, username = extract_fb_id_or_username(text)
    if not fb_id and not username:
        await update.message.reply_text("❌ একটি বৈধ Facebook প্রোফাইল লিংক দিন।")
        return
    identifier = username or fb_id
    profile_url = f"https://facebook.com/{identifier}"
    await update.message.reply_text("🔎 তথ্য আনা হচ্ছে...")

    # Graph API first
    result = fetch_profile_data_graph(identifier)
    if not result["success"]:
        result = fetch_profile_data_html(profile_url, identifier, is_id=bool(fb_id))
    if not result["success"]:
        await update.message.reply_text("😔 তথ্য আনা যায়নি: " + result.get("error", "অজানা সমস্যা"))
        return

    keyboard = [
        [
            InlineKeyboardButton("🔗 View Full Picture", url=result["image_url"]),
            InlineKeyboardButton("🌐 Go to Facebook", url=profile_url)
        ]
    ]
    caption = f"🧑‍💼 নাম: {result['name']}\n"
    if result["username"]:
        caption += f"🔖 Username: {result['username']}"
    elif result["id"]:
        caption += f"🆔 ID: {result['id']}"
    await update.message.reply_photo(
        photo=result["image_bytes"], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard)
    )

def run_telegram_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

# ----------------------------- #
#  Flask keep-alive server
# ----------------------------- #
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return jsonify({"status": "ok", "message": "Facebook Profile Bot is running"})

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# ----------------------------- #
#  Main entrypoint
# ----------------------------- #
if __name__ == "__main__":
    t = threading.Thread(target=run_telegram_bot, daemon=True)
    t.start()
    run_flask()
