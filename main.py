import sqlite3
import threading
import time
import os
import requests
from flask import Flask

# تنظیمات اصلی ربات
TOKEN = os.environ.get("TOKEN", "YOUR_BALE_TOKEN_HERE")
URL = f"https://tapi.bale.ai/bot{TOKEN}/"

# راه‌اندازی Flask برای UptimeRobot و پایش سلامت سرور
app = Flask(__name__)


@app.route("/")
def home():
    return "حاکم قلمرو - سرور فعال است! 👑"


@app.route("/health")
def health():
    return "OK", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# پینگ خودکار برای جلوگیری از خواب رفتن هاست رایگان (Render)
def self_ping():
    while True:
        time.sleep(600)  # هر 10 دقیقه
        external_url = os.environ.get("RENDER_EXTERNAL_URL")
        if external_url:
            try:
                requests.get(f"{external_url}/health")
            except:
                pass


# راه‌اندازی دیتابیس SQLite
def init_db():
    conn = sqlite3.connect("game.db", check_same_thread=False)
    cursor = conn.cursor()

    # جدول بازیکنان (سکه اولیه 180)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            chat_id INTEGER PRIMARY KEY,
            name TEXT,
            coins INTEGER DEFAULT 180,
            diamonds INTEGER DEFAULT 50,
            power INTEGER DEFAULT 15,
            soldiers INTEGER DEFAULT 0,
            meat INTEGER DEFAULT 0,
            factories INTEGER DEFAULT 0,
            butchers INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            kills INTEGER DEFAULT 0,
            territory TEXT DEFAULT 'روستای متروکه',
            clan_id INTEGER DEFAULT 0
        )
    """)

    # جدول الماس دهکده (ظرفیت حداکثر 600)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS village_resources (
            chat_id INTEGER PRIMARY KEY,
            diamonds INTEGER DEFAULT 600,
            last_diamond_regen REAL
        )
    """)

    # جدول اتحادها (Clan)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            leader_id INTEGER
        )
    """)

    conn.commit()
    conn.close()


init_db()


# تابع کمکی برای دسترسی به دیتابیس
def get_db():
    return sqlite3.connect("game.db", check_same_thread=False)


# ترد زمان‌بندی منابع
def resource_production_loop():
    while True:
        time.sleep(30)  # هر 30 ثانیه چک می‌شود
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT chat_id, factories, butchers FROM players")
        players = cursor.fetchall()

        for chat_id, factories, butchers in players:
            added_coins = factories * 5
            added_meat = butchers * 10

            cursor.execute(
                """
                UPDATE players 
                SET coins = coins + ?, meat = meat + ? 
                WHERE chat_id = ?
            """,
                (added_coins, added_meat, chat_id),
            )

            cursor.execute(
                """
                SELECT diamonds FROM village_resources WHERE chat_id = ?
            """,
                (chat_id,),
            )
            res = cursor.fetchone()
            if res:
                d_val = res[0]
                if d_val < 600:
                    new_d = min(600, d_val + 5)
                    cursor.execute(
                        """
                        UPDATE village_resources SET diamonds = ? WHERE chat_id = ?
                    """,
                        (new_d, chat_id),
                    )
            else:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO village_resources (chat_id, diamonds) VALUES (?, 600)
                """,
                    (chat_id,),
                )

        conn.commit()
        conn.close()


# تابع ارسال پیام عمومی (پشتیبانی از انواع کیبوردها)
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(URL + "sendMessage", json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")


# کیبورد اصلی ثابت (پایین صفحه)
def get_main_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🏰 وضعیت دربار"},
                {"text": "🛒 بازار سیاه (الماس)"},
            ],
            [
                {"text": "🏭 ساخت کارخانه (100 سکه)"},
                {"text": "🥩 ساخت قصابی (80 سکه)"},
            ],
            [
                {"text": "🪖 استخدام سرباز (2 گوشت)"},
                {"text": "⚔️ نبرد با بازیکنان (PvP)"},
            ],
            [
                {"text": "🛡️ اتحادها"},
            ],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


# مدیریت ورودی‌های ربات
def handle_updates():
    offset = 0
    while True:
        try:
            response = requests.get(
                URL + "getUpdates", params={"offset": offset, "timeout": 30}
            )
            data = response.json()
            if "result" in data:
                for update in data["result"]:
                    offset = update["update_id"] + 1

                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")
                        name = msg["from"].get("first_name", "حاکم")

                        process_message(chat_id, name, text)

                    elif "callback_query" in update:
                        cq = update["callback_query"]
                        chat_id = cq["message"]["chat"]["id"]
                        data_call = cq["data"]
                        name = cq["from"].get("first_name", "حاکم")

                        process_callback(chat_id, name, data_call)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


def process_message(chat_id, name, text):
    conn = get_db()
    cursor = conn.cursor()

    # ثبت نام بازیکن اگر وجود نداشت (سکه اولیه 180)
    cursor.execute("SELECT chat_id FROM players WHERE chat_id = ?", (chat_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO players (chat_id, name, coins) VALUES (?, ?, 180)",
            (chat_id, name),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO village_resources (chat_id, diamonds) VALUES (?, 600)",
            (chat_id,),
        )
        conn.commit()

    conn.close()

    if text == "/start" or text == "منو" or text == "🏰 وضعیت دربار":
        send_main_menu(chat_id, name)

    elif text == "🏭 ساخت کارخانه (100 سکه)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT coins FROM players WHERE chat_id = ?", (chat_id,))
        coins = cursor.fetchone()[0]
        if coins >= 100:
            cursor.execute(
                "UPDATE players SET coins = coins - 100, factories = factories + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(
                chat_id,
                "✅ یک کارخانه جدید ساخته شد! (هر دقیقه 10 سکه تولید می‌کند)",
                get_main_keyboard(),
            )
        else:
            send_message(
                chat_id,
                "❌ سکه کافی برای ساخت کارخانه نداری! (100 سکه نیاز است)",
                get_main_keyboard(),
            )
        conn.close()

    elif text == "🥩 ساخت قصابی (80 سکه)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT coins FROM players WHERE chat_id = ?", (chat_id,))
        coins = cursor.fetchone()[0]
        if coins >= 80:
            cursor.execute(
                "UPDATE players SET coins = coins - 80, butchers = butchers + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(
                chat_id,
                "✅ یک قصابی ساخته شد! (هر 30 ثانیه 10 گوشت تولید می‌کند)",
                get_main_keyboard(),
            )
        else:
            send_message(
                chat_id,
                "❌ سکه کافی برای ساخت قصابی نداری! (80 سکه نیاز است)",
                get_main_keyboard(),
            )
        conn.close()

    elif text == "🪖 استخدام سرباز (2 گوشت)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT meat FROM players WHERE chat_id = ?", (chat_id,))
        meat = cursor.fetchone()[0]
        if meat >= 2:
            cursor.execute(
                "UPDATE players SET meat = meat - 2, soldiers = soldiers + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(
                chat_id,
                "🪖 یک سرباز وفادار به ارتش پیوست!",
                get_main_keyboard(),
            )
        else:
            send_message(
                chat_id,
                "❌ گوشت کافی نداری! ساخت هر سرباز 2 گوشت می‌خواهد.",
                get_main_keyboard(),
            )
        conn.close()

    elif text == "🛒 بازار سیاه (الماس)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,)
        )
        res = cursor.fetchone()
        diamonds = res[0] if res else 600
        conn.close()

        market_text = (
            f"🛒 **بازار سیاه (محل داد و ستد با الماس)**\n\n"
            f"💎 الماس‌های شما: {diamonds} / 600\n\n"
            "برای خرید سکه یا گوشت از دکمه‌های زیر استفاده کنید:"
        )
        market_keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "📦 خرید 50 سکه (10 الماس)",
                        "callback_data": "buy_coins",
                    },
                    {
                        "text": "🥩 خرید 20 گوشت (15 الماس)",
                        "callback_data": "buy_meat",
                    },
                ]
            ]
        }
        send_message(chat_id, market_text, market_keyboard)

    elif text == "⚔️ نبرد با بازیکنان (PvP)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT chat_id, name, territory, soldiers FROM players WHERE chat_id != ?",
            (chat_id,),
        )
        targets = cursor.fetchall()
        conn.close()

        if not targets:
            send_message(
                chat_id,
                "⚠️ هنوز بازیکن دیگری در ربات ثبت‌نام نکرده است!",
                get_main_keyboard(),
            )
            return

        keyboard = []
        for t_id, t_name, t_terr, t_sold in targets:
            keyboard.append([
                {
                    "text": f"⚔️ حمله به {t_name} ({t_terr}) [سرباز: {t_sold}]",
                    "callback_data": f"attack_{t_id}",
                }
            ])

        send_message(
            chat_id,
            "🎯 **لیست حریفان برای حمله:**\nروی دکمه‌ی حریف مورد نظر خود کلیک کنید:",
            {"inline_keyboard": keyboard},
        )

    elif text == "🛡️ اتحادها":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT clan_id FROM players WHERE chat_id = ?", (chat_id,))
        p_clan = cursor.fetchone()[0]

        if p_clan == 0:
            cursor.execute("SELECT id, name FROM clans")
            clans = cursor.fetchall()
            conn.close()

            keyboard = [
                [{"text": "➕ ساخت اتحاد جدید", "callback_data": "create_clan"}]
            ]
            for c_id, c_name in clans:
                keyboard.append([{
                    "text": f"🛡️ پیوستن به اتحاد: {c_name}",
                    "callback_data": f"join_clan_{c_id}",
                }])

            send_message(
                chat_id,
                "🛡️ شما هنوز عضو هیچ اتحاد و قبیله‌ای نیستید.\nمی‌توانید یک اتحاد جدید بسازید یا به اتحادهای موجود بپیوندید:",
                {"inline_keyboard": keyboard},
            )
        else:
            cursor.execute("SELECT name FROM clans WHERE id = ?", (p_clan,))
            clan_res = cursor.fetchone()
            clan_name = clan_res[0] if clan_res else "اتحاد ناشناخته"

            cursor.execute(
                "SELECT name FROM players WHERE clan_id = ?", (p_clan,)
            )
            members = cursor.fetchall()
            conn.close()

            member_list = ", ".join([m[0] for m in members])
            clan_text = (
                f"🛡️ **اطلاعات اتحاد شما:**\n"
                f"🏷 نام اتحاد: {clan_name}\n"
                f"👥 اعضای اتحاد: {member_list}\n\n"
                "برای ترک اتحاد می‌توانید از دکمه زیر استفاده کنید:"
            )
            send_message(
                chat_id,
                clan_text,
                {
                    "inline_keyboard": [[
                        {"text": "🚪 ترک اتحاد", "callback_data": "leave_clan"}
                    ]]
                },
            )

    else:
        send_message(
            chat_id,
            "دستور نامعتبر! از دکمه‌های پایین صفحه استفاده کنید:",
            get_main_keyboard(),
        )


def process_callback(chat_id, name, data):
    conn = get_db()
    cursor = conn.cursor()

    if data == "buy_coins":
        cursor.execute(
            "SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,)
        )
        diamonds = cursor.fetchone()[0]
        if diamonds >= 10:
            cursor.execute(
                "UPDATE village_resources SET diamonds = diamonds - 10 WHERE chat_id = ?",
                (chat_id,),
            )
            cursor.execute(
                "UPDATE players SET coins = coins + 50 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "✅ 50 سکه با موفقیت خریداری شد!")
        else:
            send_message(chat_id, "❌ الماس کافی نداری!")

    elif data == "buy_meat":
        cursor.execute(
            "SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,)
        )
        diamonds = cursor.fetchone()[0]
        if diamonds >= 15:
            cursor.execute(
                "UPDATE village_resources SET diamonds = diamonds - 15 WHERE chat_id = ?",
                (chat_id,),
            )
            cursor.execute(
                "UPDATE players SET meat = meat + 20 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "✅ 20 گوشت با موفقیت از بازار سیاه خریداری شد!")
        else:
            send_message(chat_id, "❌ الماس کافی نداری! (15 الماس نیاز است)")

    elif data == "create_clan":
        clan_name = f"اتحاد {name}"
        cursor.execute(
            "INSERT INTO clans (name, leader_id) VALUES (?, ?)",
            (clan_name, chat_id),
        )
        clan_id = cursor.lastrowid
        cursor.execute(
            "UPDATE players SET clan_id = ? WHERE chat_id = ?",
            (clan_id, chat_id),
        )
        conn.commit()
        send_message(chat_id, f"🏰 اتحاد «{clan_name}» با موفقیت تأسیس شد!")

    elif data.startswith("join_clan_"):
        c_id = int(data.split("_")[2])
        cursor.execute(
            "UPDATE players SET clan_id = ? WHERE chat_id = ?", (c_id, chat_id)
        )
        conn.commit()
        send_message(chat_id, "🛡️ با موفقیت به اتحاد مورد نظر پیوستید!")

    elif data == "leave_clan":
        cursor.execute(
            "UPDATE players SET clan_id = 0 WHERE chat_id = ?", (chat_id,)
        )
        conn.commit()
        send_message(chat_id, "🚪 شما اتحاد خود را ترک کردید.")

    elif data.startswith("attack_"):
        target_id = int(data.split("_")[1])
        cursor.execute(
            "SELECT name, power, soldiers, coins FROM players WHERE chat_id = ?",
            (chat_id,),
        )
        attacker = cursor.fetchone()

        cursor.execute(
            "SELECT name, power, soldiers, coins FROM players WHERE chat_id = ?",
            (target_id,),
        )
        defender = cursor.fetchone()

        if not defender:
            conn.close()
            send_message(chat_id, "❌ این بازیکن دیگر در دسترس نیست.")
            return

        att_power = attacker[1] + (attacker[2] * 5)
        def_power = defender[1] + (defender[2] * 5)

        if att_power >= def_power:
            loot = min(50, defender[3])
            cursor.execute(
                "UPDATE players SET coins = coins + ?, wins = wins + 1 WHERE chat_id = ?",
                (loot, chat_id),
            )
            cursor.execute(
                "UPDATE players SET coins = coins - ?, losses = losses + 1 WHERE chat_id = ?",
                (loot, target_id),
            )
            conn.commit()
            send_message(
                chat_id,
                f"🎉 پیروزی بزرگ!\nشما به قلمرو **{defender[0]}** یورش بردید و با غلبه بر ارتش او، {loot} سکه غنیمت گرفتید!",
            )
            send_message(
                target_id,
                f"⚠️ هشدار! حاکم **{attacker[0]}** به قلمرو شما حمله کرد و شما نبرد را باختید و {loot} سکه از دست دادید!",
            )
        else:
            cursor.execute(
                "UPDATE players SET losses = losses + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            cursor.execute(
                "UPDATE players SET wins = wins + 1 WHERE chat_id = ?",
                (target_id,),
            )
            conn.commit()
            send_message(
                chat_id,
                f"💥 شکست تلخ!\nارتش شما در برابر مدافعان **{defender[0]}** شکست خورد و عقب‌نشینی کرد.",
            )
            send_message(
                target_id,
                f"🛡️ دفاع موفق!\nحاکم **{attacker[0]}** به شما حمله کرد اما دلاوران شما مانع از نفوذ او شدند!",
            )

    conn.close()


def send_main_menu(chat_id, name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT coins, meat, soldiers, factories, butchers, territory FROM players WHERE chat_id = ?",
        (chat_id,),
    )
    row = cursor.fetchone()

    cursor.execute(
        "SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,)
    )
    d_row = cursor.fetchone()
    diamonds = d_row[0] if d_row else 600
    conn.close()

    if row:
        coins, meat, soldiers, factories, butchers, territory = row
        text = (
            f"👑 سلام حاکم بزرگ، **{name}**!\n"
            f"🏰 قلمرو: {territory}\n\n"
            f"💰 سکه: {coins} | 💎 الماس: {diamonds} / 600\n"
            f"🥩 گوشت: {meat} | 🪖 سربازان: {soldiers}\n"
            f"🏭 کارخانه: {factories} (تولید: 10 سکه/دقیقه)\n"
            f"🥩 قصابی: {butchers} (تولید: 10 گوشت/30ثانیه)\n\n"
            "امپراتوری شما برقرار است. از منوی زیر گزینه‌ای را انتخاب کنید:"
        )
        send_message(chat_id, text, get_main_keyboard())


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    resource_thread = threading.Thread(target=resource_production_loop)
    resource_thread.daemon = True
    resource_thread.start()

    ping_thread = threading.Thread(target=self_ping)
    ping_thread.daemon = True
    ping_thread.start()

    handle_updates()
