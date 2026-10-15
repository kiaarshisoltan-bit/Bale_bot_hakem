import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests
import json
import time
import random
import sqlite3

# --- سرور وب برای رندر ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"Web server starting on port {port}...")
    server.serve_forever()

web_thread = threading.Thread(target=run_web_server, daemon=True)
web_thread.start()
# ---------------------------------------------------------------------

TOKEN = os.environ.get("TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# اتصال به دیتابیس SQLite
db = sqlite3.connect("game.db", check_same_thread=False)
cursor = db.cursor()

# ساخت جدول با ستون‌های جدید (سربازان)
cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER PRIMARY KEY,
    name TEXT,
    coins INTEGER DEFAULT 100,
    power INTEGER DEFAULT 15,
    soldiers INTEGER DEFAULT 0,
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

# تابع ساخت کیبورد متنی (زیر صفحه)
def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "🏰 وضعیت قلمرو"}, {"text": "💰 کارخانه سکه"}],
            [{"text": "🛡️ ساخت سرباز (۴۰ سکه)"}, {"text": "⚔️ نبرد تصادفی"}],
            [{"text": "🏆 جدول برترین‌ها"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def main():
    print("Bot is starting up with new features...")
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
                            f"سلام {user_name} عزیز! به نسخه جدید بازی «حاکم قلمرو» خوش اومدی. 👑\n\n"
                            "حالا می‌تونی سرباز بسازی، سکه جمع کنی و توی جدول برترین‌ها رقابت کنی!"
                        )
                        send_message(chat_id, welcome_text, get_main_keyboard())
                        
                    elif text == "🏰 وضعیت قلمرو":
                        cursor.execute("SELECT coins, power, soldiers, territory FROM players WHERE chat_id = ?", (chat_id,))
                        res = cursor.fetchone()
                        if res:
                            coins, power, soldiers, territory = res
                            status_text = (
                                f"🏰 قلمرو: {territory}\n"
                                f"💰 سکه‌ها: {coins}\n"
                                f"🛡️ تعداد سربازان: {soldiers}\n"
                                f"⚡ قدرت کل جنگی: {power}"
                            )
                            send_message(chat_id, status_text, get_main_keyboard())
                            
                    elif text == "💰 کارخانه سکه":
                        cursor.execute("UPDATE players SET coins = coins + 30 WHERE chat_id = ?", (chat_id,))
                        db.commit()
                        send_message(chat_id, "💰 کارخانه فعال شد و ۳۰ سکه به خزانه واریز شد!", get_main_keyboard())
                        
                    elif text == "🛡️ ساخت سرباز (۴۰ سکه)":
                        cursor.execute("SELECT coins, power, soldiers FROM players WHERE chat_id = ?", (chat_id,))
                        res = cursor.fetchone()
                        if res:
                            coins, power, soldiers = res
                            if coins >= 40:
                                cursor.execute("UPDATE players SET coins = coins - 40, soldiers = soldiers + 1, power = power + 10 WHERE chat_id = ?", (chat_id,))
                                db.commit()
                                send_message(chat_id, "🛡️ یک سرباز جدید به ارتش شما پیوست! (+۱۰ قدرت جنگی)", get_main_keyboard())
                            else:
                                send_message(chat_id, f"❌ سکه کافی نداری! برای هر سرباز به ۴۰ سکه نیاز داری. (سکه فعلی: {coins})", get_main_keyboard())
                                
                    elif text == "⚔️ نبرد تصادفی":
                        cursor.execute("SELECT power FROM players WHERE chat_id = ?", (chat_id,))
                        res = cursor.fetchone()
                        if res:
                            player_power = res[0]
                            enemy_power = random.randint(10, 40)
                            
                            if player_power >= enemy_power:
                                reward_coins = random.randint(40, 80)
                                cursor.execute("UPDATE players SET coins = coins + ?, power = power + 5 WHERE chat_id = ?", (reward_coins, chat_id))
                                db.commit()
                                send_message(chat_id, f"⚔️ نبرد پیروزمندانه بود!\n(قدرت شما: {player_power} | قدرت دشمن: {enemy_power})\n🏆 پاداش: {reward_coins} سکه و ۵ قدرت!", get_main_keyboard())
                            else:
                                send_message(chat_id, f"💥 در نبرد شکست خوردی!\n(قدرت شما: {player_power} | قدرت دشمن: {enemy_power})\nباید با ساخت سرباز قدرتت رو بیشتر کنی!", get_main_keyboard())
                                
                    elif text == "🏆 جدول برترین‌ها":
                        cursor.execute("SELECT name, coins, power FROM players ORDER BY coins DESC LIMIT 5")
                        top_players = cursor.fetchall()
                        leaderboard_text = "🏆 **۵ حاکم برتر قلمرو:**\n\n"
                        for idx, p in enumerate(top_players, 1):
                            leaderboard_text += f"{idx}. {p[0]} ➜ 💰 {p[1]} سکه | ⚡ قدرت: {p[2]}\n"
                        send_message(chat_id, leaderboard_text, get_main_keyboard())

        time.sleep(1)

if __name__ == "__main__":
    main()
