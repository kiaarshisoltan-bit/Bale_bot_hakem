import os
import sqlite3
import threading
import time
import requests
from flask import Flask

# تنظیمات ربات بله
TOKEN = "YOUR_BOT_TOKEN_HERE"  # توکن ربات بله خودت رو اینجا بذار
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# راه‌اندازی سرور Flask برای زنده نگه داشتن ربات روی Render
app = Flask(__name__)


@app.route("/")
def home():
    return "Realm Ruler Bot is running smoothly!"


@app.route("/health")
def health():
    return "OK", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# راه‌اندازی پایگاه داده SQLite
def init_db():
    conn = sqlite3.connect("game.db", check_same_thread=False)
    cursor = conn.cursor()

    # جدول بازیکنان
    cursor.execute(
        """
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
            clan_id INTEGER DEFAULT 0,
            state TEXT DEFAULT 'NORMAL'
        )
    """
    )

    # جدول منابع روستا
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS village_resources (
            chat_id INTEGER PRIMARY KEY,
            diamonds INTEGER DEFAULT 600,
            last_diamond_regen REAL
        )
    """
    )

    # جدول اتحادها
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS clans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            leader_id INTEGER
        )
    """
    )

    conn.commit()
    conn.close()


init_db()


# توابع کمکی دیتابیس
def get_db():
    return sqlite3.connect("game.db", check_same_thread=False)


# کیبوردهای اصلی و اتحاد
def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "🏰 وضعیت قلمرو"}, {"text": "🏭 کارخانه‌ها و منابع"}],
            [{"text": "⚔️ سربازخانه و نبرد"}, {"text": "🛒 بازار سیاه"}],
            [{"text": "🛡️ اتحادها"}, {"text": "📜 راهنما"}],
        ],
        "resize_keyboard": True,
    }


def get_clan_keyboard():
    return {
        "keyboard": [
            [{"text": "👥 اعضای اتحاد"}, {"text": "🚪 ترک اتحاد"}],
            [{"text": "🔙 بازگشت به منوی اصلی"}],
        ],
        "resize_keyboard": True,
    }


# ارسال پیام به بله
def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")


# ارسال پیام با کیبورد شیشه‌ای (Inline)
def send_inline_keyboard(chat_id, text, inline_keyboard):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": inline_keyboard},
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending inline message: {e}")


# حلقه تولید منابع هر ۳۰ ثانیه
def resource_production_loop():
    while True:
        time.sleep(30)
        conn = get_db()
        cursor = conn.cursor()
        try:
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

            # بازیابی الماس‌های روستا (هر ۳۰ ثانیه ۵ الماس تا سقف ۶۰۰)
            cursor.execute(
                "SELECT chat_id, diamonds FROM village_resources"
            )
            villages = cursor.fetchall()
            for chat_id, diamonds in villages:
                if diamonds < 600:
                    new_diamonds = min(600, diamonds + 5)
                    cursor.execute(
                        "UPDATE village_resources SET diamonds = ? WHERE chat_id = ?",
                        (new_diamonds, chat_id),
                    )
            conn.commit()
        except Exception as e:
            print(f"Error in resource loop: {e}")
        finally:
            conn.close()


# پینگ خودکار برای جلوگیری از خوابیدن سرویس رندر
def self_ping():
    while True:
        time.sleep(600)  # هر ۱۰ دقیقه
        try:
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                requests.get(f"{render_url}/health")
        except Exception as e:
            print(f"Self-ping error: {e}")


# پردازش پیام‌ها و دستورات ربات
def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    name = message["chat"].get("first_name", "حاکم")

    conn = get_db()
    cursor = conn.cursor()

    # بررسی ثبت‌نام بازیکن
    cursor.execute("SELECT * FROM players WHERE chat_id = ?", (chat_id,))
    player = cursor.fetchone()

    if not player:
        # ثبت‌نام بازیکن جدید با سکه اولیه ۱۸۰
        cursor.execute(
            "INSERT INTO players (chat_id, name, coins, diamonds, power, soldiers, meat, territory, clan_id, state) VALUES (?, ?, 180, 50, 15, 0, 0, 'روستای متروکه', 0, 'NORMAL')",
            (chat_id, name),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO village_resources (chat_id, diamonds, last_diamond_regen) VALUES (?, 600, ?)",
            (chat_id, time.time()),
        )
        conn.commit()
        conn.close()
        send_message(
            chat_id,
            f"👑 به بازی «حاکم قلمرو» خوش آمدید، {name}!\nبه عنوان پاداش اولیه ۱۸۰ سکه و ۵۰ الماس دریافت کردید.\nقلمرو شما آماده ساخت و ساز است!",
            reply_markup=get_main_keyboard(),
        )
        return

    # استخراج اطلاعات بازیکن
    (
        c_id,
        p_name,
        coins,
        diamonds,
        power,
        soldiers,
        meat,
        factories,
        butchers,
        wins,
        losses,
        kills,
        territory,
        clan_id,
        state,
    ) = player

    # مدیریت وضعیت‌های خاص (مثل ساخت اتحاد یا نام‌گذاری)
    if state == "WAITING_FOR_CLAN_NAME":
        clan_name = text
        cursor.execute("SELECT * FROM clans WHERE name = ?", (clan_name,))
        if cursor.fetchone():
            conn.close()
            send_message(
                chat_id,
                "⚠️ این نام اتحاد قبلاً ثبت شده است! لطفاً نام دیگری انتخاب کنید:",
            )
            return

        cursor.execute(
            "INSERT INTO clans (name, leader_id) VALUES (?, ?)",
            (clan_name, chat_id),
        )
        cursor.execute(
            "SELECT id FROM clans WHERE name = ?", (clan_name,)
        )
        new_clan = cursor.fetchone()
        new_clan_id = new_clan[0]

        cursor.execute(
            "UPDATE players SET clan_id = ?, state = 'NORMAL' WHERE chat_id = ?",
            (new_clan_id, chat_id),
        )
        conn.commit()
        conn.close()
        send_message(
            chat_id,
            f"🎉 اتحاد بزرگ «{clan_name}» با موفقیت تاسیس شد و شما رهبر آن هستید!",
            reply_markup=get_clan_keyboard(),
        )
        return

    conn.close()

    # منوها و دستورات اصلی
    if text == "🏰 وضعیت قلمرو":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT coins, diamonds, power, soldiers, meat, factories, butchers, wins, losses, territory FROM players WHERE chat_id = ?",
            (chat_id,),
        )
        p_data = cursor.fetchone()
        conn.close()

        status_text = (
            f"🏰 اطلاعات قلمرو حاکم {name}:\n\n"
            f"💰 سکه: {p_data[0]}\n"
            f"💎 الماس: {p_data[1]}\n"
            f"⚔️ قدرت کل: {p_data[2]}\n"
            f"🛡️ تعداد سربازان: {p_data[3]}\n"
            f"🥩 گوشت: {p_data[4]}\n"
            f"🏭 کارخانه‌ها: {p_data[5]}\n"
            f"🥩 قصابی‌ها: {p_data[6]}\n"
            f"🏆 پیروزی‌ها: {p_data[7]} | شکست‌ها: {p_data[8]}\n"
            f"📍 منطقه: {p_data[9]}"
        )
        send_message(chat_id, status_text, reply_markup=get_main_keyboard())

    elif text == "🏭 کارخانه‌ها و منابع":
        inline_kb = [
            [
                {"text": "🏗️ ساخت کارخانه (۵۰ سکه)", "callback_data": "build_factory"},
                {"text": "🥩 ساخت قصابی (۴۰ سکه)", "callback_data": "build_butcher"},
            ]
        ]
        send_inline_keyboard(
            chat_id,
            "🏭 بخش مدیریت تولید منابع:\nکارخانه‌ها هر دقیقه سکه و قصابی‌ها گوشت تولید می‌کنند.",
            inline_kb,
        )

    elif text == "⚔️ سربازخانه و نبرد":
        inline_kb = [
            [{"text": "🪖 استخدام سرباز (۲ گوشت)", "callback_data": "recruit_soldier"}],
            [{"text": "⚔️ جستجوی حریف برای نبرد (PvP)", "callback_data": "pvp_search"}],
        ]
        send_inline_keyboard(
            chat_id,
            "⚔️ لشکرکشی و قدرت نظامی:\nسربازان برای پیروزی در نبردها و غارت دیگران ضروری هستند.",
            inline_kb,
        )

    elif text == "🛒 بازار سیاه":
        inline_kb = [
            [{"text": "💰 خرید ۵۰ سکه (۱۰ الماس)", "callback_data": "buy_coins"}],
            [{"text": "🥩 خرید ۲۰ گوشت (۱۵ الماس)", "callback_data": "buy_meat"}],
        ]
        send_inline_keyboard(
            chat_id,
            "🛒 بازار سیاه سیاهپوشان:\nالماس‌های خود را تبدیل به سکه یا گوشت کنید.",
            inline_kb,
        )

    elif text == "🛡️ اتحادها":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT clan_id FROM players WHERE chat_id = ?", (chat_id,))
        p_clan = cursor.fetchone()[0]
        conn.close()

        if p_clan == 0:
            inline_kb = [
                [{"text": "👑 تاسیس اتحاد جدید", "callback_data": "create_clan"}],
                [{"text": "🤝 پیوستن به اتحادها", "callback_data": "join_clan_list"}],
            ]
            send_inline_keyboard(
                chat_id,
                "🛡️ شما در حال حاضر عضو هیچ اتحادی نیستید. قدرت در اتحاد است!",
                inline_kb,
            )
        else:
            send_message(
                chat_id,
                "🛡️ شما عضو یک اتحاد هستید. از منوی زیر برای مدیریت استفاده کنید:",
                reply_markup=get_clan_keyboard(),
            )

    elif text == "👥 اعضای اتحاد":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT clan_id FROM players WHERE chat_id = ?", (chat_id,))
        p_clan = cursor.fetchone()[0]
        if p_clan == 0:
            conn.close()
            send_message(
                chat_id,
                "شما عضو هیچ اتحادی نیستید.",
                reply_markup=get_main_keyboard(),
            )
            return
        cursor.execute("SELECT name, power FROM players WHERE clan_id = ?", (p_clan,))
        members = cursor.fetchall()
        conn.close()

        mem_text = "👥 اعضای اتحاد شما:\n\n"
        for m_name, m_power | in members:  # type: ignore
            mem_text += f"▪️ {m_name} (قدرت: {m_power})\n"
        send_message(chat_id, mem_text, reply_markup=get_clan_keyboard())

    elif text == "🚪 ترک اتحاد":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE players SET clan_id = 0 WHERE chat_id = ?", (chat_id,)
        )
        conn.commit()
        conn.close()
        send_message(
            chat_id,
            "🚪 شما با موفقیت از اتحاد خارج شدید.",
            reply_markup=get_main_keyboard(),
        )

    elif text == "🔙 بازگشت به منوی اصلی":
        send_message(
            chat_id, "به منوی اصلی بازگشتید.", reply_markup=get_main_keyboard()
        )

    elif text == "📜 راهنما":
        help_text = (
            "📜 راهنمای بازی «حاکم قلمرو»:\n\n"
            "۱. کارخانه‌ها و قصابی‌ها منابع شما را افزایش می‌دهند.\n"
            "۲. با گوشت، سرباز استخدام کنید تا قدرتتان بالا برود.\n"
            "۳. در بخش نبرد، حریفان را غارت کنید و سکه به دست آورید.\n"
            "۴. اتحاد بسازید یا به دیگران بپیوندید تا قدرتمندتر شوید!"
        )
        send_message(chat_id, help_text, reply_markup=get_main_keyboard())


# پردازش کلیدهای شیشه‌ای (Callback Queries)
def handle_callback(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    data = callback_query["data"]

    conn = get_db()
    cursor = conn.cursor()

    if data == "build_factory":
        cursor.execute(
            "SELECT coins, factories FROM players WHERE chat_id = ?", (chat_id,)
        )
        coins, factories = cursor.fetchone()
        if coins >= 50:
            cursor.execute(
                "UPDATE players SET coins = coins - 50, factories = factories + 1, power = power + 5 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(
                chat_id, "✅ کارخانه با موفقیت ساخته شد و قدرت شما افزایش یافت!"
            )
        else:
            send_message(
                chat_id, "❌ سکه کافی برای ساخت کارخانه ندارید (نیاز به ۵۰ سکه)."
            )

    elif data == "build_butcher":
        cursor.execute(
            "SELECT coins, butchers FROM players WHERE chat_id = ?", (chat_id,)
        )
        coins, butchers = cursor.fetchone()
        if coins >= 40:
            cursor.execute(
                "UPDATE players SET coins = coins - 40, butchers = butchers + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "✅ قصابی با موفقیت ساخته شد!")
        else:
            send_message(
                chat_id, "❌ سکه کافی برای ساخت قصابی ندارید (نیاز به ۴۰ سکه)."
            )

    elif data == "recruit_soldier":
        cursor.execute(
            "SELECT meat, soldiers FROM players WHERE chat_id = ?", (chat_id,)
        )
        meat, soldiers = cursor.fetchone()
        if meat >= 2:
            cursor.execute(
                "UPDATE players SET meat = meat - 2, soldiers = soldiers + 1, power = power + 8 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "🪖 یک سرباز شجاع به ارتش شما پیوست!")
        else:
            send_message(
                chat_id, "❌ گوشت کافی برای استخدام سرباز ندارید (نیاز به ۲ گوشت)."
            )

    elif data == "pvp_search":
        cursor.execute(
            "SELECT chat_id, name, power FROM players WHERE chat_id != ? ORDER BY RANDOM() LIMIT 1",
            (chat_id,),
        )
        target = cursor.fetchone()
        if not target:
            send_message(
                chat_id, "❌ در حال حاضر حریف دیگری برای حمله یافت نشد."
            )
        else:
            t_id, t_name, t_power = target
            cursor.execute(
                "SELECT power FROM players WHERE chat_id = ?", (chat_id,)
            )
            my_power = cursor.fetchone()[0]

            if my_power >= t_power:
                cursor.execute(
                    "UPDATE players SET coins = coins + 30, wins = wins + 1 WHERE chat_id = ?",
                    (chat_id,),
                )
                cursor.execute(
                    "UPDATE players SET coins = MAX(0, coins - 30), losses = losses + 1 WHERE chat_id = ?",
                    (t_id,),
                )
                conn.commit()
                send_message(
                    chat_id,
                    f"🎉 پیروزی در نبرد!\nشما به قلمرو {t_name} یورش بردید و ۳۰ سکه غارت کردید.",
                )
            else:
                cursor.execute(
                    "UPDATE players SET losses = losses + 1 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                send_message(
                    chat_id,
                    f"💥 شکست در نبرد!\nارتش {t_name} بسیار قدرتمندتر بود و شکست خوردید.",
                )

    elif data == "buy_coins":
        cursor.execute(
            "SELECT diamonds FROM players WHERE chat_id = ?", (chat_id,)
        )
        diamonds = cursor.fetchone()[0]
        if diamonds >= 10:
            cursor.execute(
                "UPDATE players SET diamonds = diamonds - 10, coins = coins + 50 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "💎 ۵۰ سکه با موفقیت خریداری شد!")
        else:
            send_message(
                chat_id, "❌ الماس کافی ندارید (نیاز به ۱۰ الماس در بازار سیاه)."
            )

    elif data == "buy_meat":
        cursor.execute(
            "SELECT diamonds FROM players WHERE chat_id = ?", (chat_id,)
        )
        diamonds = cursor.fetchone()[0]
        if diamonds >= 15:
            cursor.execute(
                "UPDATE players SET diamonds = diamonds - 15, meat = meat + 20 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            send_message(chat_id, "💎 ۲۰ گوشت با موفقیت خریداری شد!")
        else:
            send_message(
                chat_id, "❌ الماس کافی ندارید (نیاز به ۱۵ الماس در بازار سیاه)."
            )

    elif data == "create_clan":
        cursor.execute(
            "UPDATE players SET state = 'WAITING_FOR_CLAN_NAME' WHERE chat_id = ?",
            (chat_id,),
        )
        conn.commit()
        send_message(
            chat_id,
            "👑 لطفاً نام مورد نظر برای اتحاد خود را در قالب یک پیام ارسال کنید:",
        )

    elif data == "join_clan_list":
        cursor.execute("SELECT id, name FROM clans LIMIT 5")
        clans = cursor.fetchall()
        if not clans:
            send_message(
                chat_id, "❌ هیچ اتحادی برای پیوستن وجود ندارد. یکی بسازید!"
            )
        else:
            inline_kb = []
            for c_id_db, c_name in clans:
                inline_kb.append(
                    [
                        {
                            "text": f"پیوستن به {c_name}",
                            "callback_data": f"join_clan_{c_id_db}",
                        }
                    ]
                )
            send_inline_keyboard(chat_id, "🛡️ اتحادهای موجود:", inline_kb)

    elif data.startswith("join_clan_"):
        c_id_target = int(data.split("_")[2])
        cursor.execute(
            "UPDATE players SET clan_id = ? WHERE chat_id = ?",
            (c_id_target, chat_id),
        )
        conn.commit()
        send_message(
            chat_id,
            "🎉 شما با موفقیت به اتحاد پیوستید!",
            reply_markup=get_clan_keyboard(),
        )

    conn.close()


# حلقه دریافت آپدیت‌ها از بله (Long Polling)
def handle_updates():
    offset = 0
    print("Bot polling loop started successfully.")
    while True:
        try:
            url = f"{BASE_URL}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            if response.status_code == 200:
                data = response.json()
                for result in data.get("result", []):
                    offset = result["update_id"] + 1
                    if "message" in result:
                        handle_message(result["message"])
                    elif "callback_query" in result:
                        handle_callback(result["callback_query"])
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    # استارت سرور فلاسک در ترد جداگانه
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # ترد تولید منابع
    resource_thread = threading.Thread(target=resource_production_loop)
    resource_thread.daemon = True
    resource_thread.start()

    # ترد پینگ خودکار
    ping_thread = threading.Thread(target=self_ping)
    ping_thread.daemon = True
    ping_thread.start()

    print("Starting bot main polling loop...")
    # حلقه اصلی پویایی ربات (مانع از خروج زودهنگام برنامه در رندر می‌شود)
    handle_updates()
