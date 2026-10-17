import os
import sqlite3
import threading
import time
import requests
from flask import Flask

# تنظیمات ربات (توکن و آدرس API)
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_URL = f"https://tapi.bale.ai/bot{TOKEN}"  # یا آدرس پیام‌رسان مورد نظر

# راه‌اندازی وب‌سرور Flask برای زنده نگه داشتن ربات روی Render
app = Flask(__name__)


@app.route("/")
def home():
    return "👑 ربات حاکم قلمرو با موفقیت روشن است و کار می‌کند!"


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


# مدیریت دیتابیس SQLite
DB_NAME = "game.db"


def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # جدول بازیکنان
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            chat_id INTEGER PRIMARY KEY,
            name TEXT,
            coins INTEGER DEFAULT 100,
            diamonds INTEGER DEFAULT 50,
            power INTEGER DEFAULT 10,
            soldiers INTEGER DEFAULT 0,
            meat INTEGER DEFAULT 20,
            factories INTEGER DEFAULT 0,
            butchers INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            kills INTEGER DEFAULT 0,
            territory TEXT,
            clan_id INTEGER DEFAULT 0
        )
    """)

    # جدول منابع روستا (الماس با ظرفیت محدود ۶۰۰)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS village_resources (
            chat_id INTEGER PRIMARY KEY,
            diamonds INTEGER DEFAULT 50,
            last_diamond_regen REAL
        )
    """)

    # جدول اتحادها و قبیله‌ها
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


# مدیریت الماس‌ها و بازسازی خودکار آن‌ها (سقف ۶۰۰)
def ensure_village_resources(cursor, chat_id):
    now = time.time()
    cursor.execute(
        "SELECT diamonds, last_diamond_regen FROM village_resources WHERE chat_id = ?",
        (chat_id,),
    )
    res = cursor.fetchone()

    if not res:
        cursor.execute(
            "INSERT INTO village_resources (chat_id, diamonds, last_diamond_regen) VALUES (?, 50, ?)",
            (chat_id, now),
        )
        return 50

    diamonds, last_regen = res
    if last_regen is None:
        last_regen = now

    elapsed = now - last_regen
    if elapsed >= 30:  # هر ۳۰ ثانیه ۵ الماس
        intervals = int(elapsed // 30)
        added = intervals * 5
        diamonds = min(600, diamonds + added)
        new_regen = last_regen + (intervals * 30)
        cursor.execute(
            "UPDATE village_resources SET diamonds = ?, last_diamond_regen = ? WHERE chat_id = ?",
            (diamonds, new_regen, chat_id),
        )

    return diamonds


# حلقه تولید خودکار منابع (کارخانه و قصابی) هر ۳۰ ثانیه
def resource_production_loop():
    while True:
        time.sleep(30)
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chat_id, factories, butchers FROM players WHERE factories > 0 OR butchers > 0"
            )
            players = cursor.fetchall()

            for chat_id, factories, butchers in players:
                coin_gain = factories * 5
                meat_gain = butchers * 10
                cursor.execute(
                    "UPDATE players SET coins = coins + ?, meat = meat + ? WHERE chat_id = ?",
                    (coin_gain, meat_gain, chat_id),
                )

                # بازسازی الماس‌ها در پس‌زمینه
                ensure_village_resources(cursor, chat_id)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"خطا در حلقه تولید منابع: {e}")


# پینگ خودکار برای جلوگیری از به خواب رفتن ربات روی Render
def self_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return
    while True:
        try:
            requests.get(url, timeout=10)
        except Exception:
            pass
        time.sleep(300)  # هر ۵ دقیقه


# کیبورد اصلی ربات
def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "🏰 وضعیت امپراتوری"}, {"text": "🏭 ساخت کارخانه (100 سکه)"}],
            [
                {"text": "🥩 ساخت قصابی (80 سکه)"},
                {"text": "🪖 استخدام سرباز (2 گوشت)"},
            ],
            [{"text": "🛒 بازار سیاه"}, {"text": "⚔️ نبرد با بازیکنان (PvP)"}],
            [{"text": "🛡️ اتحادها"}],
        ],
        "resize_keyboard": True,
    }


# ارسال پیام به کاربر
def send_message(chat_id, text, reply_markup=None):
    url = f"{API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"خطا در ارسال پیام: {e}")


# پردازش پیام‌های متنی دریافتی
def process_message(chat_id, name, text):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT territory FROM players WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()

    if not row:
        # ثبت‌نام اولیه کاربر و درخواست نام قلمرو
        if text.startswith("/start"):
            send_message(
                chat_id,
                f"👑 سلام حاکم بزرگ، {name}!\nبه بازی **حاکم قلمرو** خوش آمدید.\n\nلطفاً نام دلخواه برای قلمرو خود را ارسال کنید (مثلاً: آریاشهر):",
            )
            return
        else:
            territory_name = text.strip()
            cursor.execute(
                "INSERT INTO players (chat_id, name, territory) VALUES (?, ?, ?)",
                (chat_id, name, territory_name),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                f"🎉 قلمرو «{territory_name}» با موفقیت ثبت شد!\nاکنون امپراتوری شما آغاز شده است.",
                get_main_keyboard(),
            )
            return

    conn.close()

    if text == "🏰 وضعیت امپراتوری":
        send_main_menu(chat_id, name)

    elif text == "🏭 ساخت کارخانه (100 سکه)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT coins, factories FROM players WHERE chat_id = ?", (chat_id,))
        coins, factories = cursor.fetchone()
        if coins >= 100:
            cursor.execute(
                "UPDATE players SET coins = coins - 100, factories = factories + 1, power = power + 5 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "✅ کارخانه با موفقیت ساخته شد و به قدرت شما افزوده گشت! 🏭", get_main_keyboard())
        else:
            send_message(chat_id, "❌ سکه کافی نداری! (نیاز به ۱۰۰ سکه)", get_main_keyboard())
        conn.close()

    elif text == "🥩 ساخت قصابی (80 سکه)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT coins, butchers FROM players WHERE chat_id = ?", (chat_id,))
        coins, butchers = cursor.fetchone()
        if coins >= 80:
            cursor.execute(
                "UPDATE players SET coins = coins - 80, butchers = butchers + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "✅ قصابی با موفقیت ساخته شد! 🥩", get_main_keyboard())
        else:
            send_message(chat_id, "❌ سکه کافی نداری! (نیاز به ۸۰ سکه)", get_main_keyboard())
        conn.close()

    elif text == "🪖 استخدام سرباز (2 گوشت)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT meat, soldiers FROM players WHERE chat_id = ?", (chat_id,))
        meat, soldiers = cursor.fetchone()
        if meat >= 2:
            cursor.execute(
                "UPDATE players SET meat = meat - 2, soldiers = soldiers + 1, power = power + 10 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "🪖 یک سرباز دلیر به ارتش شما پیوست!", get_main_keyboard())
        else:
            send_message(chat_id, "❌ گوشت کافی نداری! (نیاز به ۲ گوشت)", get_main_keyboard())
        conn.close()

    elif text == "🛒 بازار سیاه":
        conn = get_db()
        cursor = conn.cursor()
        diamonds = ensure_village_resources(cursor, chat_id)
        conn.commit()
        conn.close()

        market_text = (
            f"🛒 بازار سیاه (محل داد و ستد با الماس)\n\n"
            f"💎 الماس‌های شما: {diamonds} / 600\n\n"
            "برای خرید سکه یا گوشت از دکمه‌های زیر استفاده کنید:"
        )
        market_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📦 خرید 50 سکه (10 الماس)", "callback_data": "buy_coins"},
                    {"text": "🥩 خرید 20 گوشت (15 الماس)", "callback_data": "buy_meat"},
                ]
            ]
        }
        send_message(chat_id, market_text, market_keyboard)

    elif text == "⚔️ نبرد با بازیکنان (PvP)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT chat_id, name, territory, soldiers, power FROM players WHERE chat_id != ? ORDER BY RANDOM() LIMIT 1",
            (chat_id,),
        )
        enemy = cursor.fetchone()
        conn.close()

        if not enemy:
            send_message(chat_id, "⚠️ هنوز هیچ بازیکن دیگری در ربات ثبت‌نام نکرده است!", get_main_keyboard())
            return

        enemy_id, enemy_name, enemy_territory, enemy_soldiers, enemy_power = enemy
        
        # متن مشخصات کامل کاربر رندوم
        text_show = (
            "🎯 یک هدف برای نبرد شناسایی شد!\n\n"
            f"👑 نام حاکم: {enemy_name}\n"
            f"🏰 نام قلمرو: {enemy_territory}\n"
            f"🪖 تعداد سربازان: {enemy_soldiers}\n"
            f"⚔️ قدرت رزمی: {enemy_power}\n\n"
            "برای یورش به این قلمرو از دکمه زیر استفاده کن:"
        )
        
        # فقط یک دکمه شیشه‌ای تمیز بدون لیست اضافی
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": f"⚔️ نبرد با {enemy_territory} ({enemy_name})",
                        "callback_data": f"attack_random_{enemy_id}",
                    }
                ]
            ]
        }
        send_message(chat_id, text_show, keyboard)

    elif text == "🛡️ اتحادها":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT clan_id FROM players WHERE chat_id = ?", (chat_id,))
        p_clan = cursor.fetchone()[0]

        if p_clan == 0:
            cursor.execute("SELECT id, name FROM clans")
            clans = cursor.fetchall()
            conn.close()

            keyboard = [[{"text": "➕ ساخت اتحاد جدید", "callback_data": "create_clan"}]]
            for c_id, c_name in clans:
                keyboard.append([{
                    "text": f"🛡️ پیوستن به اتحاد: {c_name}",
                    "callback_data": f"join_clan_{c_id}"
                }])

            send_message(
                chat_id,
                "🛡️ شما هنوز عضو هیچ اتحاد و قبیله‌ای نیستید.\nمی‌توانید یک اتحاد جدید بسازید یا به اتحادهای موجود بپیوندید:",
                {"inline_keyboard": keyboard}
            )
        else:
            cursor.execute("SELECT name FROM clans WHERE id = ?", (p_clan,))
            clan_res = cursor.fetchone()
            clan_name = clan_res[0] if clan_res else "اتحاد ناشناخته"
            
            cursor.execute("SELECT name FROM players WHERE clan_id = ?", (p_clan,))
            members = cursor.fetchall()
            conn.close()

            member_list = ", ".join([m[0] for m in members])
            clan_text = (
                f"🛡️ اطلاعات اتحاد شما:\n"
                f"🏷 نام اتحاد: {clan_name}\n"
                f"👥 اعضای اتحاد: {member_list}\n\n"
                "برای ترک اتحاد می‌توانید از دکمه زیر استفاده کنید:"
            )
            send_message(
                chat_id,
                clan_text,
                {"inline_keyboard": [[{"text": "🚪 ترک اتحاد", "callback_data": "leave_clan"}]]}
            )
    else:
        send_message(chat_id, "دستور نامعتبر! از دکمه‌های پایین صفحه استفاده کنید:", get_main_keyboard())


# پردازش کلیک روی دکمه‌های شیشه‌ای (Inline Keyboards)
def process_callback(chat_id, name, data):
    conn = get_db()
    cursor = conn.cursor()

    if data == "buy_coins":
        diamonds = ensure_village_resources(cursor, chat_id)
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
            send_message(chat_id, "✅ ۵۰ سکه با موفقیت خریداری شد!", get_main_keyboard())
        else:
            send_message(chat_id, "❌ الماس کافی نداری!", get_main_keyboard())

    elif data == "buy_meat":
        diamonds = ensure_village_resources(cursor, chat_id)
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
            send_message(chat_id, "✅ ۲۰ گوشت با موفقیت خریداری شد!", get_main_keyboard())
        else:
            send_message(chat_id, "❌ الماس کافی نداری!", get_main_keyboard())

    elif data == "create_clan":
        clan_name = f"اتحاد {name}"
        cursor.execute("INSERT INTO clans (name, leader_id) VALUES (?, ?)", (clan_name, chat_id))
        clan_id = cursor.lastrowid
        cursor.execute("UPDATE players SET clan_id = ? WHERE chat_id = ?", (clan_id, chat_id))
        conn.commit()
        send_message(chat_id, f"🏰 اتحاد «{clan_name}» با موفقیت تأسیس شد!", get_main_keyboard())

    elif data.startswith("join_clan_"):
        c_id = int(data.split("_")[2])
        cursor.execute("UPDATE players SET clan_id = ? WHERE chat_id = ?", (c_id, chat_id))
        conn.commit()
        send_message(chat_id, "🛡️ با موفقیت به اتحاد مورد نظر پیوستید!", get_main_keyboard())

    elif data == "leave_clan":
        cursor.execute("UPDATE players SET clan_id = 0 WHERE chat_id = ?", (chat_id,))
        conn.commit()
        send_message(chat_id, "🚪 شما اتحاد خود را ترک کردید.", get_main_keyboard())

    elif data.startswith("attack_random_"):
        target_id = int(data.split("_")[2])

        cursor.execute(
            "SELECT name, power, soldiers, coins FROM players WHERE chat_id = ?",
            (chat_id,)
        )
        attacker = cursor.fetchone()

        cursor.execute(
            "SELECT name, power, soldiers, coins FROM players WHERE chat_id = ?",
            (target_id,)
        )
        defender = cursor.fetchone()

        if not defender or not attacker:
            send_message(chat_id, "❌ این قلمرو دیگر وجود ندارد!", get_main_keyboard())
            conn.close()
            return

        att_name, att_power_base, att_soldiers, att_coins = attacker
        def_name, def_power_base, def_soldiers, def_coins = defender

        att_power = att_power_base + (att_soldiers * 10)
        def_power = def_power_base + (def_soldiers * 10)

        if att_power >= def_power:
            loot = min(50, def_coins)
            cursor.execute(
                "UPDATE players SET coins = coins + ?, wins = wins + 1 WHERE chat_id = ?",
                (loot, chat_id)
            )
            new_def_coins = max(0, def_coins - loot)
            cursor.execute(
                "UPDATE players SET coins = ?, losses = losses + 1 WHERE chat_id = ?",
                (new_def_coins, target_id)
            )
            conn.commit()

            send_message(
                chat_id,
                f"🎉 پیروزی بزرگ!\nقلمرو {def_name} را شکست دادی و {loot} سکه غنیمت گرفتی!",
                get_main_keyboard()
            )
            send_message(
                target_id,
                f"⚠️ هشدار!\nحاکم {att_name} به قلمرو شما حمله کرد و شما نبرد را باختید و {loot} سکه از دست دادید!",
                get_main_keyboard()
            )
        else:
            cursor.execute(
                "UPDATE players SET losses = losses + 1 WHERE chat_id = ?",
                (chat_id,)
            )
            cursor.execute(
                "UPDATE players SET wins = wins + 1 WHERE chat_id = ?",
                (target_id,)
            )
            conn.commit()

            send_message(
                chat_id,
                f"💥 شکست خوردی!\nارتش {def_name} قوی‌تر بود و مجبور به عقب‌نشینی شدی.",
                get_main_keyboard()
            )
            send_message(
                target_id,
                f"🛡️ دفاع موفق!\nحاکم {att_name} به شما حمله کرد اما دلاوران شما مانع نفوذ او شدند!",
                get_main_keyboard()
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

    diamonds = ensure_village_resources(cursor, chat_id)
    conn.commit()
    conn.close()

    if row:
        coins, meat, soldiers, factories, butchers, territory = row
        text = (
            f"👑 سلام حاکم بزرگ، {name}!\n"
            f"🏰 قلمرو: {territory}\n\n"
            f"💰 سکه: {coins} | 💎 الماس: {diamonds} / 600\n"
            f"🥩 گوشت: {meat} | 🪖 سربازان: {soldiers}\n"
            f"🏭 کارخانه: {factories} (تولید: 5 سکه/30ثانیه)\n"
            f"🥩 قصابی: {butchers} (تولید: 10 گوشت/30ثانیه)\n\n"
            "امپراتوری شما برقرار است. از منوی زیر گزینه‌ای را انتخاب کنید:"
        )
        send_message(chat_id, text, get_main_keyboard())


# حلقه دریافت آپدیت‌ها از پیام‌رسان (Long Polling)
def handle_updates():
    offset = 0
    print("🤖 ربات با موفقیت آماده دریافت پیام‌ها شد...")
    while True:
        try:
            url = f"{API_URL}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            data = response.json()

            if "result" in data:
                for update in data["result"]:
                    offset = update["update_id"] + 1

                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        name = msg["from"].get("first_name", "حاکم")
                        text = msg.get("text", "")
                        process_message(chat_id, name, text)

                    elif "callback_query" in update:
                        cq = update["callback_query"]
                        chat_id = cq["message"]["chat"]["id"]
                        name = cq["from"].get("first_name", "حاکم")
                        data_val = cq["data"]
                        process_callback(chat_id, name, data_val)

        except Exception as e:
            print(f"خطا در دریافت آپدیت‌ها: {e}")
            time.sleep(3)


if __name__ == "__main__":
    # اجرای وب‌سرور Flask در یک ترد جداگانه
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # اجرای حلقه تولید منابع در ترد جداگانه
    resource_thread = threading.Thread(target=resource_production_loop)
    resource_thread.daemon = True
    resource_thread.start()

    # اجرای حلقه Self-Ping برای فعال نگه داشتن ربات روی Render
    ping_thread = threading.Thread(target=self_ping)
    ping_thread.daemon = True
    ping_thread.start()

    # اجرای حلقه اصلی دریافت پیام‌ها
    handle_updates()
