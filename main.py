import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests
import json
import time
import random
import sqlite3

# --- بخش اول: سرور وب کوچک برای فریب دادن رندر (جلوگیری از خطای پورت و نگه داشتن ربات) ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def log_message(self, format, *args):
        # این خط باعث میشه لاگ‌های اضافی سرور وب، لاگ‌های اصلی رباتت رو شلوغ نکنه
        return

def run_web_server():
    # رندر پورت رو از طریق متغیر محیطی میگه، اگر نبود از 10000 استفاده کن
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"Web server starting on port {port}...")
    server.serve_forever()

# اجرای سرور وب در پس‌زمینه به محض شروع برنامه
web_thread = threading.Thread(target=run_web_server, daemon=True)
web_thread.start()
# ---------------------------------------------------------------------

# تنظیمات ربات بله
# حتماً در پنل رندر در قسمت Environment Variables، متغیر TOKEN رو تعریف کن
TOKEN = os.environ.get("TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# اتصال به دیتابیس SQLite
db = sqlite3.connect("game.db", check_same_thread=False)
cursor = db.cursor()

# ساخت جدول کاربران و قلمروها اگر وجود نداشته باشند
cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER PRIMARY KEY,
    name TEXT,
    coins INTEGER DEFAULT 100,
    power INTEGER DEFAULT 10,
    territory TEXT DEFAULT 'روستای متروکه'
)
""")
db.commit()

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        response = requests.get(url, params=params, timeout=35)
        return response.json()
    except Exception as e:
        print(f"Error getting updates: {e}")
        return None

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

def main():
    print("Bot is starting up...")
    offset = None
    
    while True:
        updates = get_updates(offset)
        if updates and "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1
                
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    user_name = message["from"].get("first_name", "بازیکن")
                    text = message.get("text", "")
                    
                    # ثبت نام خودکار بازیکن در دیتابیس
                    cursor.execute("SELECT * FROM players WHERE chat_id = ?", (chat_id,))
                    player = cursor.fetchone()
                    if not player:
                        cursor.execute("INSERT INTO players (chat_id, name) VALUES (?, ?)", (chat_id, user_name))
                        db.commit()
                        
                    if text == "/start":
                        welcome_text = (
                            f"سلام {user_name} عزیز! به بازی «حاکم قلمرو» خوش اومدی. 👑\n\n"
                            "قلمرو خودت رو بساز، سکه جمع کن و با بقیه بجنگ تا حاکم مطلق بشی!"
                        )
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "🏰 وضعیت قلمرو", "callback_data": "status"}, {"text": "💰 کارخانه سکه", "callback_data": "coins"}],
                                [{"text": "⚔️ نبرد تصادفی", "callback_data": "battle"}]
                            ]
                        }
                        send_message(chat_id, welcome_text, keyboard)
                        
                elif "callback_query" in update:
                    query = update["callback_query"]
                    chat_id = query["message"]["chat"]["id"]
                    data = query["data"]
                    
                    if data == "status":
                        cursor.execute("SELECT coins, power, territory FROM players WHERE chat_id = ?", (chat_id,))
                        res = cursor.fetchone()
                        if res:
                            coins, power, territory = res
                            status_text = f"🏰 قلمرو: {territory}\n💰 سکه‌ها: {coins}\n⚡ قدرت جنگی: {power}"
                            send_message(chat_id, status_text)
                        
                    elif data == "coins":
                        cursor.execute("UPDATE players SET coins = coins + 20 WHERE chat_id = ?", (chat_id,))
                        db.commit()
                        send_message(chat_id, "💰 کارخانه کار کرد و 20 سکه به خزانه اضافه شد!")
                        
                    elif data == "battle":
                        cursor.execute("SELECT power FROM players WHERE chat_id = ?", (chat_id,))
                        res = cursor.fetchone()
                        if res:
                            player_power = res[0]
                            enemy_power = random.randint(5, 25)
                            
                            if player_power >= enemy_power:
                                cursor.execute("UPDATE players SET coins = coins + 50, power = power + 5 WHERE chat_id = ?", (chat_id,))
                                db.commit()
                                send_message(chat_id, f"⚔️ نبرد پیروزمندانه بود! (قدرت شما: {player_power} | قدرت دشمن: {enemy_power})\nپاداش: 50 سکه و 5 قدرت!")
                            else:
                                send_message(chat_id, f"💥 در نبرد شکست خوردی! (قدرت شما: {player_power} | قدرت دشمن: {enemy_power})\nنیاز به تقویت قدرت داری!")

        time.sleep(1)

if __name__ == "__main__":
    main()
