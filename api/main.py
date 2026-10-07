from flask import Flask, request
import os
import requests
import re
from bs4 import BeautifulSoup

app = Flask(__name__)

# --- কনফিগারেশন ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ফেসবুক অ্যাপ ক্রেডেনশিয়াল (অপশনাল)
FB_APP_ID = os.environ.get("FB_APP_ID")
FB_APP_SECRET = os.environ.get("FB_APP_SECRET")

# --- ১. হেল্পার ফাংশন: টেলিগ্রাম ---
def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=payload)
    except Exception as e:
        print(f"Telegram Send Error: {e}")

def send_photo(chat_id, photo_url, caption, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(f"{BASE_URL}/sendPhoto", json=payload)
    except Exception as e:
        # ছবি পাঠাতে ব্যর্থ হলে টেক্সট পাঠানো হবে
        send_message(chat_id, f"{caption}\n\n⚠️ ছবি লোড করা যায়নি (Privacy/Error).")

# --- ২. হেল্পার ফাংশন: ফেসবুক ---
def get_fb_identifier(url):
    """ফেসবুক লিংক থেকে ইউজারনেম বা আইডি বের করা"""
    regex = r"(?:https?://)?(?:www\.|m\.|web\.)?facebook\.com/(?:profile\.php\?id=(?P<id>\d+)|(?P<username>[^/?&#]+))"
    match = re.search(regex, url.strip())
    if match:
        return match.group("id") or match.group("username")
    return None

def fetch_via_graph_api(identifier):
    """Facebook Graph API দিয়ে ডাটা আনা"""
    if not FB_APP_ID or not FB_APP_SECRET:
        return None
    
    try:
        access_token = f"{FB_APP_ID}|{FB_APP_SECRET}"
        fields = "name,username,id,picture.type(large)"
        url = f"https://graph.facebook.com/{identifier}?fields={fields}&access_token={access_token}"
        
        r = requests.get(url, timeout=5)
        data = r.json()
        
        if "error" in data:
            print("GRAPH ERROR:", data["error"])
            return None
        
        return {
            "name": data.get("name", "Unknown"),
            "username": data.get("username", "N/A"),
            "id": data.get("id"),
            "image": data.get("picture", {}).get("data", {}).get("url")
        }
    except:
        return None

def fetch_via_html(url):
    """HTML Scraping (Backup Method)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        # mbasic.facebook.com ব্যবহার করা ভালো স্ক্র্যাপিংয়ের জন্য
        mobile_url = url.replace("www.facebook.com", "mbasic.facebook.com")
        r = requests.get(mobile_url, headers=headers, timeout=10)
        
        soup = BeautifulSoup(r.text, "html.parser")
        
        print("HTML:", r.status_code, r.url, soup.title.text if soup.title else None)
        
        # মেটা ট্যাগ থেকে ডাটা খোঁজা
        name = soup.find("title").text if soup.find("title") else "Unknown User"
        image = None
        
        meta_img = soup.find("meta", property="og:image")
        if meta_img:
            image = meta_img["content"]
            
        return {
            "name": name,
            "username": "Hidden/Unknown",
            "id": "Hidden",
            "image": image
        }
    except:
        return None

# --- ৩. মেইন রাউট ---
@app.route('/')
def home():
    return "Facebook Profile Bot Running! 🚀"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        if "message" not in data: return "ok", 200

        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        # --- কমান্ড হ্যান্ডলিং ---
        if text == "/start":
            welcome_msg = (
                "👋 <b>স্বাগতম!</b>\n\n"
                "আমাকে ফেসবুক প্রোফাইল লিংক দিন, আমি বিস্তারিত তথ্য দেখানোর চেষ্টা করব।\n\n"
                "👉 <b>উদাহরণ:</b>\n"
                "<code>https://www.facebook.com/zuck</code>"
            )
            send_message(chat_id, welcome_msg)
        
        # --- লিংক প্রসেসিং ---
        elif "facebook.com" in text:
            identifier = get_fb_identifier(text)
            
            if not identifier:
                send_message(chat_id, "⚠️ লিংকটি সঠিক ফরম্যাটে নেই।")
                return "ok", 200

            send_message(chat_id, "🔎 তথ্য খোঁজা হচ্ছে... একটু অপেক্ষা করুন।")

            # ধাপ ১: গ্রাফ এপিআই দিয়ে চেষ্টা
            profile_data = fetch_via_graph_api(identifier)
            source = "Graph API"
            
            # ধাপ ২: না পেলে HTML স্ক্র্যাপিং
            if not profile_data:
                profile_data = fetch_via_html(text)
                source = "Web Scraping"

            if profile_data and profile_data.get("image"):
                caption = (
                    f"👤 <b>Name:</b> {profile_data['name']}\n"
                    f"🆔 <b>ID:</b> <code>{profile_data.get('id')}</code>\n"
                    f"🔗 <b>Username:</b> {profile_data.get('username')}\n"
                    f"⚙️ <b>Source:</b> {source}"
                )
                
                # বাটন তৈরি (JSON Format)
                buttons = {
                    "inline_keyboard": [[
                        {"text": "🔗 View Profile", "url": text}
                    ]]
                }
                
                send_photo(chat_id, profile_data['image'], caption, buttons)
            else:
                send_message(chat_id, "❌ দুঃখিত! ফেসবুকের প্রাইভেসি সেটিংসের কারণে তথ্য পাওয়া যায়নি।")

        else:
            send_message(chat_id, "দয়া করে একটি সঠিক <b>Facebook Link</b> দিন।")

        return "ok", 200

    except Exception as e:
        print(f"Error: {e}")
        return "error", 200
            
