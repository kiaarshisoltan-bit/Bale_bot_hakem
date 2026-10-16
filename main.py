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

    # جدول بازیکنان
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            chat_id INTEGER PRIMARY KEY,
            name TEXT,
            coins INTEGER DEFAULT 100,
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

        cursor.execute(
            "SELECT chat_id, factories, butchers FROM players"
        )
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


# تابع ارسال پیام با کیبورد متنی (پایین صفحه)
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(URL + "sendMessage", json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")


# کیبورد اصلی پایین صفحه (Reply Keyboard)
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


# مدیریت پیام‌ها و دستورات ربات بله
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
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


def process_message(chat_id, name, text):
    conn = get_db()
    cursor = conn.cursor()

    # ثبت نام بازیکن اگر وجود نداشت
    cursor.execute(
        "SELECT chat_id FROM players WHERE chat_id = ?", (chat_id,)
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO players (chat_id, name) VALUES (?, ?)", (chat_id, name)
        )
        cursor.execute(
            "INSERT OR IGNORE INTO village_resources (chat_id, diamonds) VALUES (?, 600)",
            (chat_id,),
        )
        conn.commit()

    conn.close()

    if text == "/start" or text == "منو":
        send_main_menu(chat_id, name)

    elif text == "🏰 وضعیت دربار":
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
            "برای خرید هر آیتم، دستور زیر را ارسال کنید یا از دکمه‌های شیشه‌ای استفاده کنید (یا برای سادگی، با دستورات متنی خرید کنید):\n"
            "• `/buy_coins` (خرید 50 سکه با 10 الماس)\n"
            "• `/buy_meat` (خرید 20 گوشت با 15 الماس)\n"
            "• `/buy_power` (افزایش 10 قدرت با 30 الماس)"
        )
        send_message(chat_id, market_text, get_main_keyboard())

    elif text == "/buy_coins":
        conn = get_db()
        cursor = conn.cursor()
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
                "UPDATE players SET coins = coins + 50 WHERE chat_id = ?", (chat_id,)
            )
            conn.commit()
            send_message(
                chat_id,
                "✅ 50 سکه با موفقیت خریداری شد!",
                get_main_keyboard(),
            )
        else:
            send_message(chat_id, "❌ الماس کافی نداری!", get_main_keyboard())
        conn.close()

    elif text == "/buy_meat":
        conn = get_db()
        cursor = conn.cursor()
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
                "UPDATE players SET meat = meat + 20 WHERE chat_id = ?", (chat_id,)
            )
            conn.commit()
            send_message(
                chat_id,
                "✅ 20 گوشت با موفقیت از بازار سیاه خریداری شد!",
                get_main_keyboard(),
            )
        else:
            send_message(
                chat_id,
                "❌ الماس کافی نداری! (15 الماس نیاز است)",
                get_main_keyboard(),
            )
        conn.close()

    elif text == "/buy_power":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,)
        )
        diamonds = cursor.fetchone()[0]
        if diamonds >= 30:
            cursor.execute(
                "UPDATE village_resources SET diamonds = diamonds - 30 WHERE chat_id = ?",
                (chat_id,),
            )
            cursor.execute(
                "UPDATE players SET power = power + 10 WHERE chat_id = ?", (chat_id,),
            )
            conn.commit()
            send_message(
                chat_id,
                "✅ تجهیزات جنگی خریداری شد! قدرت شما 10 واحد افزایش یافت.",
                get_main_keyboard(),
            )
        else:
            send_message(chat_id, "❌ الماس کافی نداری!", get_main_keyboard())
        conn.close()

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

        target_list_text = (
            "🎯 **لیست حریفان برای حمله:**\nبرای حمله به هر بازیکن، دستور زیر را ارسال کنید:\n"
        )
        for t_id, t_name, t_terr, t_sold in targets:
            target_list_text += (
                f"• نام: {t_name} | قلمرو: {t_terr} | سرباز: {t_sold}\n"
                f"  دستور حمله: `/attack_{t_id}`\n\n"
            )
        send_message(chat_id, target_list_text, get_main_keyboard())

    elif text.startswith("/attack_"):
        try:
            target_id = int(text.split("_")[1])
        except:
            send_message(chat_id, "❌ فرمت حمله نامعتبر است.", get_main_keyboard())
            return

        conn = get_db()
        cursor = conn.cursor()
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
            send_message(
                chat_id,
                "❌ این بازیکن دیگر در دسترس نیست.",
                get_main_keyboard(),
            )
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
                get_main_keyboard(),
            )
            send_message(
                target_id,
                f"⚠️ هشدار! حاکم **{attacker[0]}** به قلمرو شما حمله کرد و شما نبرد را باختید و {loot} سکه از دست دادید!",
                get_main_keyboard(),
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
                get_main_keyboard(),
            )
            send_message(
                target_id,
                f"🛡️ دفاع موفق!\nحاکم **{attacker[0]}** به شما حمله کرد اما دلاوران شما مانع از نفوذ او شدند!",
                get_main_keyboard(),
            )
        conn.close()

    elif text == "🛡️ اتحادها":
        send_message(
            chat_id,
            "🛡️ سیستم اتحادها و قبیله‌ها به زودی فعال خواهد شد تا با دوستانتان متحد شوید!",
            get_main_keyboard(),
        )

    else:
        send_message(
            chat_id,
            "دستور نامعتبر! از دکمه‌های پایین صفحه استفاده کنید:",
            get_main_keyboard(),
        )


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
