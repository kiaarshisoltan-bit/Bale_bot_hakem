import os
import threading
import requests
import json
import random
import sqlite3
import time
from flask import Flask, render_template_string, request, jsonify

# --- راه‌اندازی سرور Flask برای وب‌اپ و سلامت سرور ---
app = Flask(__name__)

@app.route('/health')
def health_check():
    """مسیر اختصاصی و فوق‌العاده سریع برای جلوگیری از بلاک شدن و پینگ UptimeRobot"""
    return "OK", 200

# اتصال به دیتابیس SQLite
def get_db_connection():
    conn = sqlite3.connect("game.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ساخت جدول دیتابیس
db = sqlite3.connect("game.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER PRIMARY KEY,
    name TEXT,
    coins INTEGER DEFAULT 100,
    power INTEGER DEFAULT 15,
    soldiers INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    kills INTEGER DEFAULT 0,
    territory TEXT DEFAULT 'روستای متروکه'
)
""")
db.commit()

# صفحه گرافیکی وب‌اپ (HTML / CSS)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>حاکم قلمرو - مدیریت قلعه</title>
    <style>
        body {
            background-color: #1a1a2e;
            color: #e94560;
            font-family: Tahoma, sans-serif;
            text-align: center;
            padding: 20px;
            margin: 0;
        }
        .container {
            max-width: 400px;
            margin: auto;
            background: #16213e;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.4);
            border: 2px solid #0f3460;
        }
        h1 {
            color: #f7cb15;
            font-size: 24px;
            margin-bottom: 5px;
        }
        .subtitle {
            color: #a0a0a0;
            font-size: 13px;
            margin-bottom: 20px;
        }
        .stats-card {
            background: #0f3460;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            color: #fff;
            text-align: right;
            border-right: 5px solid #e94560;
        }
        .stat-item {
            margin: 8px 0;
            font-size: 15px;
        }
        .btn {
            background-color: #e94560;
            color: white;
            border: none;
            padding: 12px 20px;
            margin: 8px 0;
            width: 100%;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            font-weight: bold;
            transition: 0.2s;
        }
        .btn:active {
            transform: scale(0.97);
        }
        .btn-factory { background-color: #f7cb15; color: #1a1a2e; }
        .btn-soldier { background-color: #00b4d8; }
        .btn-battle { background-color: #e63946; }
    </style>
</head>
<body>
    <div class="container">
        <h1>👑 حاکم قلمرو</h1>
        <div class="subtitle">پنل مدیریت سلطنتی</div>

        <div class="stats-card">
            <div class="stat-item">🏰 <b>قلمرو:</b> <span id="territory">{{ territory }}</span></div>
            <div class="stat-item">💰 <b>سکه‌ها:</b> <span id="coins">{{ coins }}</span></div>
            <div class="stat-item">🛡️ <b>سربازان:</b> <span id="soldiers">{{ soldiers }}</span></div>
            <div class="stat-item">⚡ <b>قدرت جنگی:</b> <span id="power">{{ power }}</span></div>
            <div class="stat-item">⚔️ <b>برد / باخت:</b> {{ wins }} برد | {{ losses }} باخت</div>
            <div class="stat-item">💀 <b>دشمنان کشته:</b> {{ kills }}</div>
        </div>

        <button class="btn btn-factory" onclick="doAction('factory')">💰 کارخانه سکه (+۳۰)</button>
        <button class="btn btn-soldier" onclick="doAction('soldier')">🛡️ ساخت سرباز (۴۰ سکه)</button>
        <button class="btn btn-battle" onclick="doAction('battle')">⚔️ نبرد تصادفی</button>
    </div>

    <script>
        const chatId = "{{ chat_id }}";

        function doAction(actionType) {
            fetch('/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId, action: actionType })
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    document.getElementById('coins').innerText = data.coins;
                    document.getElementById('soldiers').innerText = data.soldiers;
                    document.getElementById('power').innerText = data.power;
                    alert(data.message);
                } else {
                    alert(data.message);
                }
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def web_app():
    chat_id = request.args.get('chat_id', default=1, type=int)
    conn = get_db_connection()
    player = conn.execute("SELECT * FROM players WHERE chat_id = ?", (chat_id,)).fetchone()
    
    if not player:
        conn.execute("INSERT INTO players (chat_id, name) VALUES (?, ?)", (chat_id, "بازیکن وب"))
        conn.commit()
        player = conn.execute("SELECT * FROM players WHERE chat_id = ?", (chat_id,)).fetchone()
    
    conn.close()
    
    return render_template_string(
        HTML_TEMPLATE,
        chat_id=player['chat_id'],
        territory=player['territory'],
        coins=player['coins'],
        soldiers=player['soldiers'],
        power=player['power'],
        wins=player['wins'],
        losses=player['losses'],
        kills=player['kills']
    )

@app.route('/action', methods=['POST'])
def handle_action():
    data = request.json
    chat_id = data.get('chat_id')
    action = data.get('action')
    
    conn = get_db_connection()
    player = conn.execute("SELECT * FROM players WHERE chat_id = ?", (chat_id,)).fetchone()
    
    if not player:
        conn.close()
        return jsonify({"success": False, "message": "بازیکن یافت نشد!"})
    
    coins = player['coins']
    soldiers = player['soldiers']
    power = player['power']
    wins = player['wins']
    losses = player['losses']
    kills = player['kills']
    
    message = ""
    if action == 'factory':
        coins += 30
        conn.execute("UPDATE players SET coins = ? WHERE chat_id = ?", (coins, chat_id))
        conn.commit()
        message = "💰 کارخانه فعال شد و ۳۰ سکه واریز شد!"
        
    elif action == 'soldier':
        if coins >= 40:
            coins -= 40
            soldiers += 1
            power += 10
            conn.execute("UPDATE players SET coins = ?, soldiers = ?, power = ? WHERE chat_id = ?", (coins, soldiers, power, chat_id))
            conn.commit()
            message = "🛡️ یک سرباز جدید به ارتش شما پیوست!"
        else:
            conn.close()
            return jsonify({"success": False, "message": f"❌ سکه کافی نداری! (سکه فعلی: {coins})"})
            
    elif action == 'battle':
        enemy_power = random.randint(10, 40)
        if power >= enemy_power:
            reward_coins = random.randint(40, 80)
            enemy_kills_earned = random.randint(1, 5)
            coins += reward_coins
            power += 5
            wins += 1
            kills += enemy_kills_earned
            conn.execute("UPDATE players SET coins = ?, power = ?, wins = ?, kills = ? WHERE chat_id = ?", (coins, power, wins, kills, chat_id))
            conn.commit()
            message = f"⚔️ پیروزی در نبرد!\nپاداش: {reward_coins} سکه و {enemy_kills_earned} کشته!"
        else:
            losses += 1
            conn.execute("UPDATE players SET losses = ? WHERE chat_id = ?", (losses, chat_id))
            conn.commit()
            message = f"💥 شکست در نبرد!\nقدرت شما: {power} | قدرت دشمن: {enemy_power}"
            
    conn.close()
    return jsonify({
        "success": True,
        "coins": coins,
        "soldiers": soldiers,
        "power": power,
        "message": message
    })

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def self_ping():
    """پینگ خودکار هر ۱۰ دقیقه برای بیدار نگه داشتن سرور در رندر"""
    time.sleep(15)  # کمی صبر می‌کنیم تا سرور بالا بیاید
    app_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not app_url:
        return
    health_url = f"{app_url}/health"
    
    while True:
        try:
            time.sleep(600)  # هر ۶۰۰ ثانیه (۱۰ دقیقه)
            requests.get(health_url, timeout=10)
            print("Self-ping sent successfully.")
        except Exception as e:
            print(f"Self-ping error: {e}")

# اجرای وب‌سرور و پینگ خودکار در تردهای جداگانه
web_thread = threading.Thread(target=run_flask_server, daemon=True)
web_thread.start()

ping_thread = threading.Thread(target=self_ping, daemon=True)
ping_thread.start()
# ---------------------------------------------------------------------

TOKEN = os.environ.get("TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

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
    print("Bot is starting up with Flask WebApp support...")
    offset = None
    app_url = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")

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
                    
                    cursor = db.cursor()
                    cursor.execute("SELECT * FROM players WHERE chat_id = ?", (chat_id,))
                    player = cursor.fetchone()
                    if not player:
                        cursor.execute("INSERT INTO players (chat_id, name) VALUES (?, ?)", (chat_id, user_name))
                        db.commit()
                        
                    if text == "/start":
                        user_webapp_url = f"{app_url}/?chat_id={chat_id}"
                        
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "🌐 ورود به پنل گرافیکی قلمرو", "url": user_webapp_url}]
                            ]
                        }
                        
                        welcome_text = (
                            f"سلام {user_name} عزیز! 👑\n"
                            "به نسخه گرافیکی و مدرن **«حاکم قلمرو»** خوش اومدی.\n\n"
                            "برای مدیریت قلعه، ارتش و نبردها، روی دکمه زیر بزن تا پنل گرافیکی برات باز بشه!"
                        )
                        send_message(chat_id, welcome_text, keyboard)

        time.sleep(1)

if __name__ == "__main__":
    main()
