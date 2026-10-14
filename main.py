import sqlite3
import requests
import json
import time
import random

# --- تنظیمات ---
TOKEN = "TOKEN_BOT"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

# --- دیتابیس ---
conn = sqlite3.connect('evil_game.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                kingdom_name TEXT UNIQUE,
                gold INTEGER, factories INTEGER, factory_cost INTEGER,
                soldiers INTEGER, power INTEGER, moves INTEGER, last_income_time REAL)''')
conn.commit()

# --- سیستم درآمد ---
def check_passive_income(chat_id):
    c = conn.cursor()
    c.execute('SELECT gold, factories, last_income_time FROM users WHERE chat_id=?', (chat_id,))
    data = c.fetchone()
    if not data: return 0
    gold, factories, last_income_time = data
    
    current_time = time.time()
    elapsed_time = current_time - last_income_time
    
    if factories > 0 and elapsed_time >= 5: 
        intervals = int(elapsed_time // 5)
        earned_gold = intervals * factories * 10
        new_time = last_income_time + (intervals * 5)
        c.execute('UPDATE users SET gold = gold + ?, last_income_time = ? WHERE chat_id=?', (earned_gold, new_time, chat_id))
        conn.commit()
        return earned_gold
    return 0

# --- توابع ---
def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    requests.post(BASE_URL + "sendMessage", json=payload)

def handle_game_action(chat_id, action):
    check_passive_income(chat_id)
    c = conn.cursor()
    c.execute('SELECT gold, factories, factory_cost, soldiers, power, moves, kingdom_name FROM users WHERE chat_id=?', (chat_id,))
    data = c.fetchone()
    gold, factories, cost, soldiers, power, moves, name = data
    
    msg = f"🏛 حاکم قلمرو: {name}\n"
    
    if action == "build":
        if gold >= cost:
            new_cost = cost + 20
            c.execute('UPDATE users SET gold=gold-?, factories=factories+1, factory_cost=?, moves=moves+1 WHERE chat_id=?', (cost, new_cost, chat_id))
            msg += "✅ کارخانه ساخته شد!"
        else:
            msg += f"❌ طلا کم است! نیاز به {cost} طلا."
            
    elif action == "soldier":
        s_cost = 50 + (soldiers * 10)
        if gold >= s_cost:
            c.execute('UPDATE users SET gold=gold-?, soldiers=soldiers+1, power=power+10, moves=moves+1 WHERE chat_id=?', (s_cost, chat_id))
            msg += "💂 سرباز استخدام شد!"
        else:
            msg += f"❌ طلا کم است! نیاز به {s_cost} طلا."
            
    elif action == "battle":
        c.execute('SELECT chat_id, kingdom_name, gold, power FROM users WHERE chat_id != ? ORDER BY RANDOM() LIMIT 1', (chat_id,))
        opponent = c.fetchone()
        
        if not opponent:
            msg += "❌ فعلاً حریفی در قلمرو نیست!"
        else:
            opp_id, opp_name, opp_gold, opp_power = opponent
            if power >= opp_power:
                loot = max(10, int(opp_gold * 0.1))
                c.execute('UPDATE users SET gold = gold + ? WHERE chat_id = ?', (loot, chat_id))
                c.execute('UPDATE users SET gold = gold - ? WHERE chat_id = ?', (loot, opp_id))
                msg += f"🎉 پیروز شدی! به قلمرو '{opp_name}' حمله کردی و {loot} طلا غارت کردی!"
            else:
                msg += f"💀 شکست خوردی! قدرتِ حریف '{opp_name}' بیشتر بود."
                
    elif action == "stats":
        # اینجا متغیر power رو جایگزین p کردم
        msg += f"💰 طلا: {gold}\n🏭 کارخانه: {factories}\n💂 سرباز: {soldiers}\n⚔️ قدرت: {power}"
    
    conn.commit()
    
    keyboard = {"inline_keyboard": [
        [{"text": "🏭 ساخت", "callback_data": "build"}, {"text": "💂 سرباز", "callback_data": "soldier"}],
        [{"text": "⚔️ نبرد آنلاین", "callback_data": "battle"}, {"text": "📊 وضعیت", "callback_data": "stats"}]
    ]}
    send_message(chat_id, msg, keyboard)

# --- حلقه اصلی ---
def main():
    print("بات 'حاکم قلمرو' با موفقیت فعال شد!")
    last_update_id = None
    while True:
        try:
            updates = requests.get(BASE_URL + "getUpdates", params={"offset": last_update_id, "timeout": 30}).json()
            if updates.get("result"):
                for update in updates["result"]:
                    last_update_id = update["update_id"] + 1
                    
                    if "message" in update:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"].get("text", "")
                        c.execute('SELECT kingdom_name FROM users WHERE chat_id=?', (chat_id,))
                        user = c.fetchone()
                        
                        if text == "/start":
                            if user: send_message(chat_id, "خوش برگشتی حاکم!")
                            else: send_message(chat_id, "به بازی 'حاکم قلمرو' خوش اومدی! یه اسم برای قلمروت انتخاب کن:")
                        elif not user:
                            try:
                                c.execute('INSERT INTO users VALUES (?, ?, 100, 0, 50, 0, 0, 0, ?)', (chat_id, text, time.time()))
                                conn.commit()
                                send_message(chat_id, f"قلمرو '{text}' با موفقیت ثبت شد!")
                                # اینجا بعد از ثبت‌نام، وضعیت رو نمایش میدیم تا دکمه‌ها بیاد
                                handle_game_action(chat_id, "stats")
                            except sqlite3.IntegrityError:
                                send_message(chat_id, "این اسم قبلاً توسط شخص دیگه‌ای برداشته شده! اسم دیگه انتخاب کن.")
                                
                    elif "callback_query" in update:
                        chat_id = update["callback_query"]["message"]["chat"]["id"]
                        handle_game_action(chat_id, update["callback_query"]["data"])
                        
        except Exception as e:
            print(f"خطا: {e}")

if __name__ == "__main__":
    main()
