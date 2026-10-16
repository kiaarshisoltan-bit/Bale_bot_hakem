import os
import sqlite3
import threading
import time
import requests
from flask import Flask

# تنظیمات بات بله (Bale Bot Token)
# توکن خود را اینجا قرار دهید یا از متغیرهای محیطی Render بخوانید
TOKEN = os.environ.get("BALE_TOKEN", "YOUR_BALE_BOT_TOKEN_HERE")
API_URL = f"https://tapi.bale.ai/bot{TOKEN}"

DB_NAME = "game.db"

# راه‌اندازی سرور Flask برای زنده نگه داشتن سرویس روی Render
app = Flask(__name__)


@app.route("/")
def home():
    return "Realm Ruler Bot is running actively! 🏰"


@app.route("/health")
def health():
    return "OK", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# مدیریت دیتابیس
def get_db():
    conn = sqlite3.connect(DB_NAME)
    return conn


def init_db():
    conn = get_db()
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


# ارسال پیام در بله
def send_message(chat_id, text, reply_markup=None):
    url = f"{API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")


# ویرایش پیام (برای دکمه‌های شیشه‌ای)
def edit_message(chat_id, message_id, text, reply_markup=None):
    url = f"{API_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error editing message: {e}")


# کیبورد اصلی بازی (پایین صفحه)
def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "🏰 وضعیت دربار"}, {"text": "🏭 ساخت‌وساز"}],
            [{"text": "🛒 بازار سیاه"}, {"text": "⚔️ میدان نبرد (PvP)"}],
            [{"text": "🛡️ اتحادها"}, {"text": "📜 راهنما"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


# کیبورد مدیریت اتحاد (پایین صفحه وقتی کاربر داخل اتحاد است)
def get_clan_keyboard():
    return {
        "keyboard": [
            [{"text": "👥 اعضا"}, {"text": "📊 آمار اتحاد"}],
            [{"text": "🚪 ترک اتحاد"}, {"text": "🏰 وضعیت دربار"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


# لوپ تولید منابع هر ۳۰ ثانیه
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

            for p in players:
                chat_id, factories, butchers = p[0], p[1], p[2]
                coin_gain = factories * 5  # هر کارخانه ۵ سکه در ۳۰ ثانیه
                meat_gain = butchers * 10  # هر قصابی ۱۰ گوشت در ۳۰ ثانیه

                cursor.execute(
                    "UPDATE players SET coins = coins + ?, meat = meat + ? WHERE chat_id = ?",
                    (coin_gain, meat_gain, chat_id),
                )

            # بازیابی الماس روستاها (حداکثر ۶۰۰ الماس، هر ۳۰ ثانیه ۵ الماس)
            cursor.execute("SELECT chat_id, diamonds FROM village_resources")
            villages = cursor.fetchall()
            for v in villages:
                v_id, diamonds = v[0], v[1]
                if diamonds < 600:
                    new_d = min(600, diamonds + 5)
                    cursor.execute(
                        "UPDATE village_resources SET diamonds = ? WHERE chat_id = ?",
                        (new_d, v_id),
                    )

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error in resource loop: {e}")


# پینگ خودکار خود برای جلوگیری از خوابیدن سرویس روی Render
def self_ping():
    while True:
        time.sleep(600)  # هر ۱۰ دقیقه
        try:
            # آدرس وب‌سرویس خود را روی رندر جایگزین کنید یا بگذارید روی لوکال بماند
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                requests.get(f"{render_url}/health", timeout=10)
        except Exception as e:
            print(f"Self-ping error: {e}")


# پردازش پیام‌های متنی دریافتی
def process_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    name = message["from"].get("first_name", "حاکم")

    # ثبت نام خودکار بازیکن اگر وجود نداشته باشد
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, state, clan_id FROM players WHERE chat_id = ?", (chat_id,))
    player = cursor.fetchone()

    if not player:
        cursor.execute(
            "INSERT INTO players (chat_id, name) VALUES (?, ?)", (chat_id, name)
        )
        cursor.execute(
            "INSERT INTO village_resources (chat_id, diamonds) VALUES (?, 600)", (chat_id,)
        )
        conn.commit()
        player_state = "NORMAL"
        player_clan = 0
    else:
        player_state = player[1]
        player_clan = player[2]
    conn.close()

    # بررسی حالت‌های انتظار ورودی (مثل نام اتحاد)
    if player_state == "WAITING_CLAN_NAME":
        clan_name = text.strip()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM clans WHERE name = ?", (clan_name,))
        if cursor.fetchone():
            conn.close()
            send_message(
                chat_id,
                "❌ این نام قبلاً برای اتحاد دیگری انتخاب شده است! لطفاً نام دیگری را ارسال کنید:",
            )
        else:
            cursor.execute(
                "INSERT INTO clans (name, leader_id) VALUES (?, ?)", (clan_name, chat_id)
            )
            clan_id = cursor.lastrowid
            cursor.execute(
                "UPDATE players SET clan_id = ?, state = 'NORMAL' WHERE chat_id = ?",
                (clan_id, chat_id),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                f"🏰 اتحاد «{clan_name}» با موفقیت ساخته شد و شما رهبر آن شدید!",
                get_clan_keyboard(),
            )
        return

    elif player_state == "WAITING_JOIN_CLAN_NAME":
        clan_name = text.strip()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM clans WHERE name = ?", (clan_name,))
        clan_res = cursor.fetchone()
        if not clan_res:
            conn.close()
            send_message(
                chat_id,
                f"❌ اتحادی با نام «{clan_name}» پیدا نشد! لطفاً دوباره نام صحیح اتحاد را ارسال کنید:",
            )
        else:
            c_id = clan_res[0]
            cursor.execute(
                "UPDATE players SET clan_id = ?, state = 'NORMAL' WHERE chat_id = ?",
                (c_id, chat_id),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                f"🛡️ شما با موفقیت وارد اتحاد «{clan_name}» شدید!",
                get_clan_keyboard(),
            )
        return

    # دستورات منوی اصلی
    if text in ["/start", "📜 راهنما"]:
        welcome_text = (
            f"👑 سلام **{name}** عزیز به بازی **حاکم قلمرو** خوش آمدی!\n\n"
            "قلمرو خود را بساز، ارتش جمع کن، با کارخانه‌ها و قصابی‌ها ثروت تولید کن، با دیگر حاکمان بجنگ و قوی‌ترین امپراتوری را بنا کن!\n\n"
            "از دکمه‌های زیر برای مدیریت قلمرو استفاده کن:"
        )
        kb = get_clan_keyboard() if player_clan != 0 else get_main_keyboard()
        send_message(chat_id, welcome_text, kb)

    elif text == "🏰 وضعیت دربار":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT coins, diamonds, power, soldiers, meat, factories, butchers, wins, losses, territory FROM players WHERE chat_id = ?",
            (chat_id,),
        )
        p = cursor.fetchone()

        # خواندن الماس روستا
        cursor.execute("SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,))
        v_res = cursor.fetchone()
        v_diamonds = v_res[0] if v_res else 600
        conn.close()

        status_text = (
            f"🏰 **دبار حاکم {name}**\n\n"
            f"🪙 سکه: {p[0]}\n"
            f"💎 الماس‌های قلمرو: {p[1]} (ذخیره روستا: {v_diamonds}/600)\n"
            f"🥩 گوشت: {p[4]}\n"
            f"⚔️ قدرت رزمی: {p[2]}\n"
            f"🛡️ سربازان: {p[3]}\n"
            f"🏭 کارخانه‌ها: {p[5]} (تولید سکه)\n"
            f"🥩 قصابی‌ها: {p[6]} (تولید گوشت)\n"
            f"🏆 پیروزی‌ها: {p[7]} | 💥 شکست‌ها: {p[8]}\n"
            f"📍 قلمرو فعلی: {p[9]}"
        )
        kb = get_clan_keyboard() if player_clan != 0 else get_main_keyboard()
        send_message(chat_id, status_text, kb)

    elif text == "🏭 ساخت‌وساز":
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🏭 ساخت کارخانه (۵۰ سکه)", "callback_data": "build_factory"},
                    {"text": "🥩 ساخت قصابی (۴۰ سکه)", "callback_data": "build_butcher"},
                ],
                [
                    {"text": "🗡️ استخدام سرباز (۲ گوشت)", "callback_data": "recruit_soldier"}
                ],
            ]
        }
        send_message(
            chat_id,
            "🏭 **بخش سازندگی و ارتش:**\nکارخانه سکه می‌سازد، قصابی گوشت تولید می‌کند و گوشت برای سربازگیری نیاز است!",
            keyboard,
        )

    elif text == "🛒 بازار سیاه":
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "💎 خرید ۵۰ سکه (۱۰ الماس)", "callback_data": "buy_coins"},
                    {"text": "🥩 خرید ۲۰ گوشت (۱۵ الماس)", "callback_data": "buy_meat"},
                ]
            ]
        }
        send_message(
            chat_id,
            "🛒 **بازار سیاه قلمرو:**\nبا الماس‌های ارزشمندت می‌تونی سکه یا گوشت بخوای!",
            keyboard,
        )

    elif text == "⚔️ میدان نبرد (PvP)":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT chat_id, name, power, soldiers FROM players WHERE chat_id != ?",
            (chat_id,),
        )
        targets = cursor.fetchall()
        conn.close()

        if not targets:
            send_message(chat_id, "⚔️ حاکم دیگری هنوز در بازی ثبت‌نام نکرده است!")
            return

        inline_kb = []
        for t in targets:
            t_id, t_name, t_power, t_soldiers = t[0], t[1], t[2], t[3]
            inline_kb.append(
                [
                    {
                        "text": f"⚔️ حمله به {t_name} (قدرت: {t_power + t_soldiers * 5})",
                        "callback_data": f"attack_{t_id}",
                    }
                ]
            )

        send_message(
            chat_id,
            "⚔️ **میدان جنگ:**\nیکی از حاکمان زیر را برای حمله و غارت انتخاب کن:",
            {"inline_keyboard": inline_kb},
        )

    elif text in ["🛡️ اتحادها", "🚪 ترک اتحاد", "👥 اعضا", "📊 آمار اتحاد"]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT clan_id FROM players WHERE chat_id = ?", (chat_id,))
        p_clan = cursor.fetchone()[0]
        conn.close()

        if p_clan != 0:
            if text == "🚪 ترک اتحاد":
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE players SET clan_id = 0 WHERE chat_id = ?", (chat_id,)
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "🚪 شما با موفقیت اتحاد خود را ترک کردید.",
                    get_main_keyboard(),
                )
                return

            elif text == "👥 اعضا":
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM players WHERE clan_id = ?", (p_clan,))
                members = cursor.fetchall()
                conn.close()
                member_list = "\n".join([f"👤 {m[0]}" for m in members])
                send_message(chat_id, f"👥 **اعضای اتحاد شما:**\n\n{member_list}", get_clan_keyboard())
                return

            elif text == "📊 آمار اتحاد":
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM clans WHERE id = ?", (p_clan,))
                c_res = cursor.fetchone()
                c_name = c_res[0] if c_res else "ناشناخته"
                cursor.execute(
                    "SELECT COUNT(*), SUM(wins), SUM(losses) FROM players WHERE clan_id = ?",
                    (p_clan,),
                )
                stats = cursor.fetchone()
                conn.close()

                count, wins, losses = stats[0], stats[1] or 0, stats[2] or 0
                stat_text = (
                    f"📊 **آمار اتحاد {c_name}:**\n\n"
                    f"👥 تعداد اعضا: {count}\n"
                    f"🏆 مجموع پیروزی‌ها: {wins}\n"
                    f"💥 مجموع شکست‌ها: {losses}"
                )
                send_message(chat_id, stat_text, get_clan_keyboard())
                return

        if p_clan == 0:
            # کاربر بدون اتحاد است -> نمایش گزینه ساخت یا پیوستن
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "➕ ساخت اتحاد جدید", "callback_data": "start_create_clan"},
                        {"text": "🛡️ پیوستن به اتحاد", "callback_data": "start_join_clan"},
                    ]
                ]
            }
            send_message(
                chat_id,
                "🛡️ شما هنوز عضو هیچ اتحاد و قبیله‌ای نیستید. یکی از گزینه‌های زیر را انتخاب کنید:",
                keyboard,
            )
        else:
            send_message(
                chat_id,
                "🛡️ شما در حال حاضر عضو یک اتحاد هستید:",
                get_clan_keyboard(),
            )


# پردازش کلیک روی دکمه‌های شیشه‌ای (Inline Keyboards)
def process_callback(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    data = callback_query["data"]

    conn = get_db()
    cursor = conn.cursor()

    if data == "build_factory":
        cursor.execute("SELECT coins FROM players WHERE chat_id = ?", (chat_id,))
        coins = cursor.fetchone()[0]
        if coins >= 50:
            cursor.execute(
                "UPDATE players SET coins = coins - 50, factories = factories + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            edit_message(
                chat_id, message_id, "✅ کارخانه با موفقیت ساخته شد و به تولید سکه آغاز کرد!"
            )
        else:
            edit_message(chat_id, message_id, "❌ سکه کافی برای ساخت کارخانه نداری! (۵۰ سکه نیاز است)")

    elif data == "build_butcher":
        cursor.execute("SELECT coins FROM players WHERE chat_id = ?", (chat_id,))
        coins = cursor.fetchone()[0]
        if coins >= 40:
            cursor.execute(
                "UPDATE players SET coins = coins - 40, butchers = butchers + 1 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            edit_message(
                chat_id, message_id, "✅ قصابی با موفقیت ساخته شد و شروع به تولید گوشت کرد!"
            )
        else:
            edit_message(chat_id, message_id, "❌ سکه کافی نداری! (۴۰ سکه نیاز است)")

    elif data == "recruit_soldier":
        cursor.execute("SELECT meat FROM players WHERE chat_id = ?", (chat_id,))
        meat = cursor.fetchone()[0]
        if meat >= 2:
            cursor.execute(
                "UPDATE players SET meat = meat - 2, soldiers = soldiers + 1, power = power + 5 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            edit_message(
                chat_id, message_id, "⚔️ یک سرباز جدید با قدرت جنگی بالا به ارتش شما پیوست!"
            )
        else:
            edit_message(chat_id, message_id, "❌ گوشت کافی نداری! (هر سرباز ۲ واحد گوشت می‌خواهد)")

    elif data == "buy_coins":
        cursor.execute("SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,))
        v_d = cursor.fetchone()[0]
        if v_d >= 10:
            cursor.execute(
                "UPDATE village_resources SET diamonds = diamonds - 10 WHERE chat_id = ?",
                (chat_id,),
            )
            cursor.execute(
                "UPDATE players SET coins = coins + 50 WHERE chat_id = ?", (chat_id,)
            )
            conn.commit()
            edit_message(chat_id, message_id, "💎 معامله موفق! ۵۰ سکه به خزانه اضافه شد.")
        else:
            edit_message(chat_id, message_id, "❌ الماس روستا کافی نیست! (۱۰ الماس نیاز است)")

    elif data == "buy_meat":
        cursor.execute("SELECT diamonds FROM village_resources WHERE chat_id = ?", (chat_id,))
        v_d = cursor.fetchone()[0]
        if v_d >= 15:
            cursor.execute(
                "UPDATE village_resources SET diamonds = diamonds - 15 WHERE chat_id = ?",
                (chat_id,),
            )
            cursor.execute(
                "UPDATE players SET meat = meat + 20 WHERE chat_id = ?", (chat_id,)
            )
            conn.commit()
            edit_message(chat_id, message_id, "🥩 معامله موفق! ۲۰ واحد گوشت دریافت کردید.")
        else:
            edit_message(chat_id, message_id, "❌ الماس روستا کافی نیست! (۱۵ الماس نیاز است)")

    elif data == "start_create_clan":
        cursor.execute("UPDATE players SET state = 'WAITING_CLAN_NAME' WHERE chat_id = ?", (chat_id,))
        conn.commit()
        edit_message(chat_id, message_id, "✍️ لطفاً نام مورد نظر برای اتحاد خود را در قالب پیام متنی ارسال کنید:")

    elif data == "start_join_clan":
        cursor.execute("UPDATE players SET state = 'WAITING_JOIN_CLAN_NAME' WHERE chat_id = ?", (chat_id,))
        conn.commit()
        edit_message(chat_id, message_id, "✍️ لطفاً نام دقیق اتحادی که می‌خواهید به آن بپیوندید را ارسال کنید:")

    elif data.startswith("attack_"):
        target_id = int(data.split("_")[1])
        cursor.execute("SELECT power, soldiers, coins FROM players WHERE chat_id = ?", (chat_id,))
        attacker = cursor.fetchone()
        att_power = attacker[0] + attacker[1] * 5

        cursor.execute("SELECT name, power, soldiers, coins FROM players WHERE chat_id = ?", (target_id,))
        defender = cursor.fetchone()
        def_power = defender[1] + defender[2] * 5

        if att_power >= def_power:
            loot = min(30, defender[3])
            cursor.execute("UPDATE players SET coins = coins + ?, wins = wins + 1 WHERE chat_id = ?", (loot, chat_id))
            cursor.execute("UPDATE players SET coins = coins - ?, losses = losses + 1 WHERE chat_id = ?", (loot, target_id))
            conn.commit()
            edit_message(chat_id, message_id, f"🏆 شما در نبرد پیروز شدید و {loot} سکه از {defender[0]} غارت کردید!")
            send_message(target_id, f"⚠️ حاکم قلمرو شما مورد حمله قرار گرفت و شکست خورد! مقدار {loot} سکه غارت شد.")
        else:
            cursor.execute("UPDATE players SET losses = losses + 1 WHERE chat_id = ?", (chat_id,))
            cursor.execute("UPDATE players SET wins = wins + 1 WHERE chat_id = ?", (target_id,))
            conn.commit()
            edit_message(chat_id, message_id, f"💥 در این نبرد شکست خوردید! ارتش {defender[0]} بسیار قوی‌تر بود.")

    conn.close()


# لوپ اصلی دریافت آپدیت‌ها از بله (Long Polling)
def handle_updates():
    offset = 0
    print("Bot polling started successfully...")
    while True:
        try:
            response = requests.get(
                f"{API_URL}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            data = response.json()
            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    if "message" in update:
                        process_message(update["message"])
                    elif "callback_query" in update:
                        process_callback(update["callback_query"])
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    init_db()

    # اجرای سرور فلاسک در ترد جداگانه
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # اجرای ترد تولید منابع
    res_thread = threading.Thread(target=resource_production_loop)
    res_thread.daemon = True
    res_thread.start()

    # اجرای ترد پینگ خودکار
    ping_thread = threading.Thread(target=self_ping)
    ping_thread.daemon = True
    ping_thread.start()

    # اجرای لوپ اصلی دریافت پیام‌ها
    handle_updates()
