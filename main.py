import os
import sqlite3
import threading
import time
import requests
from flask import Flask

# تنظیمات بات بله
TOKEN = os.environ.get("BALE_TOKEN", "YOUR_BOT_TOKEN_HERE")
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# تنظیمات سرور وب برای زنده نگه داشتن روی Render
app = Flask(__name__)


@app.route("/")
def home():
    return "حاکم قلمرو بیدار است و حکومت می‌کند! 👑"


@app.route("/health")
def health():
    return "OK", 200


# دیتابیس SQLite
DB_NAME = "game.db"
db_lock = threading.Lock()


def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_NAME)
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

        # جدول منابع روستا (الماس)
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


# ارسال پیام در بله
def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")


# کیبورد اصلی شبیه منوی بازی
def get_main_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🏰 قلمرو من"},
                {"text": "⛏️ منابع و کارخانه‌ها"},
            ],
            [
                {"text": "⚔️ نبرد PvP"},
                {"text": "👥 اتحادها"},
            ],
            [
                {"text": "🛒 بازار سیاه"},
                {"text": "📜 راهنما"},
            ],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


# کیبورد منابع و کارخانه‌ها
def get_resources_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🏭 ساخت کارخانه (۵۰ سکه)"},
                {"text": "🥩 ساخت قصابی (۴۰ سکه)"},
            ],
            [
                {"text": "🛡️ استخدام سرباز (۱۰ گوشت)"},
                {"text": "🔙 بازگشت به منوی اصلی"},
            ],
        ],
        "resize_keyboard": True,
    }


# کیبورد بازار سیاه
def get_market_keyboard():
    return {
        "keyboard": [
            [
                {"text": "💎 خرید ۵۰ سکه (۱۰ الماس)"},
                {"text": "💎 خرید ۲۰ گوشت (۱۵ الماس)"},
            ],
            [{"text": "🔙 بازگشت به منوی اصلی"}],
        ],
        "resize_keyboard": True,
    }


# کیبورد اتحادها
def get_clan_keyboard(in_clan=False):
    if in_clan:
        return {
            "keyboard": [
                [
                    {"text": "👥 اعضای اتحاد"},
                    {"text": "📊 آمار اتحاد"},
                ],
                [
                    {"text": "🚪 ترک اتحاد"},
                    {"text": "🔙 بازگشت به منوی اصلی"},
                ],
            ],
            "resize_keyboard": True,
        }
    else:
        return {
            "keyboard": [
                [
                    {"text": "🏗️ ساخت اتحاد جدید"},
                    {"text": "🤝 پیوستن به اتحاد"},
                ],
                [{"text": "🔙 بازگشت به منوی اصلی"}],
            ],
            "resize_keyboard": True,
        }


# پردازش تولید منابع در پس‌زمینه (هر ۳۰ ثانیه)
def resource_production_loop():
    while True:
        time.sleep(30)
        with db_lock:
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT chat_id, factories, butchers FROM players WHERE factories > 0 OR butchers > 0"
                )
                rows = cursor.fetchall()

                for chat_id, factories, butchers in rows:
                    coin_gain = factories * 5  # هر کارخانه ۵ سکه در ۳۰ ثانیه
                    meat_gain = butchers * 10  # هر قصابی ۱۰ گوشت در ۳۰ ثانیه
                    cursor.execute(
                        "UPDATE players SET coins = coins + ?, meat = meat + ? WHERE chat_id = ?",
                        (coin_gain, meat_gain, chat_id),
                    )

                # بازسازی الماس روستاها (حداکثر ۶۰۰)
                cursor.execute(
                    "SELECT chat_id, diamonds FROM village_resources"
                )
                v_rows = cursor.fetchall()
                for chat_id, diamonds in v_rows:
                    if diamonds < 600:
                        new_d = min(600, diamonds + 5)
                        cursor.execute(
                            "UPDATE village_resources SET diamonds = ? WHERE chat_id = ?",
                            (new_d, chat_id),
                        )

                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error in resource loop: {e}")


# پینگ خودکار برای جلوگیری از خوابیدن سرویس روی Render
def self_ping():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        return
    while True:
        time.sleep(600)  # هر ۱۰ دقیقه
        try:
            requests.get(f"{render_url}/health", timeout=10)
        except Exception as e:
            print(f"Self-ping error: {e}")


# مدیریت پیام‌ها و دستورات بات
def handle_message(message):
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()
    user_name = message.get("from", {}).get("first_name", "حاکم")

    if not chat_id:
        return

    with db_lock:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # بررسی ثبت‌نام بازیکن
        cursor.execute(
            "SELECT coins, diamonds, power, soldiers, meat, factories, butchers, territory, clan_id, state FROM players WHERE chat_id = ?",
            (chat_id,),
        )
        player = cursor.fetchone()

        if not player:
            cursor.execute(
                "INSERT INTO players (chat_id, name, coins) VALUES (?, ?, 180)",
                (chat_id, user_name),
            )
            cursor.execute(
                "INSERT INTO village_resources (chat_id, diamonds) VALUES (?, 600)",
                (chat_id,),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                f"به بازی **حاکم قلمرو** خوش آمدی، {user_name}! 👑\n\nتعداد ۱۸۰ سکه اولیه به تو هدیه داده شد. قلمرو خود را بساز و بر سرزمین‌ها حکومت کن!",
                reply_markup=get_main_keyboard(),
            )
            return

        (
            coins,
            diamonds,
            power,
            soldiers,
            meat,
            factories,
            butchers,
            territory,
            clan_id,
            state,
        ) = player

        # مدیریت حالت ساخت اتحاد
        if state == "WAITING_CLAN_NAME":
            clan_name = text
            if clan_name.startswith("🔙"):
                cursor.execute(
                    "UPDATE players SET state = 'NORMAL' WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "عملیات لغو شد.",
                    reply_markup=get_clan_keyboard(clan_id > 0),
                )
                return

            try:
                cursor.execute(
                    "INSERT INTO clans (name, leader_id) VALUES (?, ?)",
                    (clan_name, chat_id),
                )
                conn.commit()
                cursor.execute(
                    "SELECT id FROM clans WHERE name = ?", (clan_name,)
                )
                new_clan = cursor.fetchone()
                cursor.execute(
                    "UPDATE players SET clan_id = ?, state = 'NORMAL' WHERE chat_id = ?",
                    (new_clan[0], chat_id),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    f"🎉 اتحاد '{clan_name}' با موفقیت تأسیس شد و تو رهبر آن شدی!",
                    reply_markup=get_clan_keyboard(True),
                )
            except sqlite3.IntegrityError:
                conn.close()
                send_message(
                    chat_id,
                    "❌ این نام اتحاد قبلاً ثبت شده است! لطفاً نام دیگری انتخاب کن:",
                )
            return

        # مدیریت حالت انتخاب حریف برای نبرد PvP
        if state.startswith("ATTACKING_"):
            target_id = int(state.split("_")[1])
            cursor.execute(
                "UPDATE players SET state = 'NORMAL' WHERE chat_id = ?",
                (chat_id,),
            )

            cursor.execute(
                "SELECT name, power, soldiers, coins FROM players WHERE chat_id = ?",
                (target_id,),
            )
            target = cursor.fetchone()

            if not target:
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "❌ حریف مورد نظر یافت نشد.",
                    reply_markup=get_main_keyboard(),
                )
                return

            t_name, t_power, t_soldiers, t_coins = target
            my_total_power = power + (soldiers * 5)
            target_total_power = t_power + (t_soldiers * 5)

            if my_total_power >= target_total_power:
                loot = min(50, t_coins)
                cursor.execute(
                    "UPDATE players SET coins = coins + ?, wins = wins + 1, kills = kills + 1 WHERE chat_id = ?",
                    (loot, chat_id),
                )
                cursor.execute(
                    "UPDATE players SET coins = coins - ?, losses = losses + 1 WHERE chat_id = ?",
                    (loot, target_id),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    f"⚔️ **پیروزی در نبرد!**\n\nتو به قلمرو **{t_name}** یورش بردی و با قدرت بیشتر پیروز شدی!\n💰 مقدار **{loot} سکه** غنیمت گرفتی.",
                    reply_markup=get_main_keyboard(),
                )
                send_message(
                    target_id,
                    f"⚠️ قلمرو شما توسط **{user_name}** مورد حمله قرار گرفت و شکست خوردید! 💰 {loot} سکه غارت شد.",
                )
            else:
                cursor.execute(
                    "UPDATE players SET losses = losses + 1 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    f"💀 **شکست در نبرد!**\n\nارتش **{t_name}** بسیار قدرتمندتر بود و شکست سنگینی خوردی.",
                    reply_markup=get_main_keyboard(),
                )
            return

        # دستورات اصلی منو
        if text == "/start" or text == "🔙 بازگشت به منوی اصلی":
            cursor.execute(
                "UPDATE players SET state = 'NORMAL' WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                "به منوی اصلی حاکم قلمرو خوش آمدید! گزینه‌ی مورد نظر را انتخاب کنید:",
                reply_markup=get_main_keyboard(),
            )

        elif text == "🏰 قلمرو من":
            cursor.execute(
                "SELECT wins, losses, kills FROM players WHERE chat_id = ?",
                (chat_id,),
            )
            stats = cursor.fetchone()
            conn.close()
            wins, losses, kills = stats
            info = (
                f"🏰 **اطلاعات قلمرو حاکم {user_name}**\n\n"
                f"💰 سکه‌ها: {coins}\n"
                f"💎 الماس‌ها: {diamonds}\n"
                f"🥩 گوشت: {meat}\n"
                f"⚔️ قدرت پایه: {power}\n"
                f"🛡️ سربازان: {soldiers}\n"
                f"🏭 کارخانه‌ها: {factories}\n"
                f"🥩 قصابی‌ها: {butchers}\n"
                f"🏆 پیروزی‌ها: {wins} | شکست‌ها: {losses}\n"
                f"📍 قلمرو فعلی: {territory}"
            )
            send_message(chat_id, info, reply_markup=get_main_keyboard())

        elif text == "⛏️ منابع و کارخانه‌ها":
            conn.close()
            send_message(
                chat_id,
                "⛏️ **مدیریت منابع و تولید**\n\n"
                "کارخانه‌ها هر دقیقه سکه و قصابی‌ها گوشت تولید می‌کنند. برای تقویت ارتش و قلمرو اقدام کنید:",
                reply_markup=get_resources_keyboard(),
            )

        elif text == "🏭 ساخت کارخانه (۵۰ سکه)":
            if coins >= 50:
                cursor.execute(
                    "UPDATE players SET coins = coins - 50, factories = factories + 1 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "✅ یک کارخانه جدید با موفقیت ساخته شد!",
                    reply_markup=get_resources_keyboard(),
                )
            else:
                conn.close()
                send_message(
                    chat_id,
                    "❌ سکه کافی نداری! (نیاز به ۵۰ سکه)",
                    reply_markup=get_resources_keyboard(),
                )

        elif text == "🥩 ساخت قصابی (۴۰ سکه)":
            if coins >= 40:
                cursor.execute(
                    "UPDATE players SET coins = coins - 40, butchers = butchers + 1 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "✅ یک قصابی جدید ساخته شد!",
                    reply_markup=get_resources_keyboard(),
                )
            else:
                conn.close()
                send_message(
                    chat_id,
                    "❌ سکه کافی نداری! (نیاز به ۴۰ سکه)",
                    reply_markup=get_resources_keyboard(),
                )

        elif text == "🛡️ استخدام سرباز (۱۰ گوشت)":
            if meat >= 10:
                cursor.execute(
                    "UPDATE players SET meat = meat - 10, soldiers = soldiers + 1, power = power + 5 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "🪖 یک سرباز جدید به ارتش ملحق شد! قدرت نظامی افزایش یافت.",
                    reply_markup=get_resources_keyboard(),
                )
            else:
                conn.close()
                send_message(
                    chat_id,
                    "❌ گوشت کافی نداری! (نیاز به ۱۰ گوشت)",
                    reply_markup=get_resources_keyboard(),
                )

        elif text == "🛒 بازار سیاه":
            conn.close()
            send_message(
                chat_id,
                "🛒 **بازار سیاه حاکم قلمرو**\n\nمی‌توانید با الماس‌های خود منابع خریداری کنید:",
                reply_markup=get_market_keyboard(),
            )

        elif text == "💎 خرید ۵۰ سکه (۱۰ الماس)":
            cursor.execute(
                "SELECT diamonds FROM village_resources WHERE chat_id = ?",
                (chat_id,),
            )
            res = cursor.fetchone()
            v_diamonds = res[0] if res else 0

            if v_diamonds >= 10:
                cursor.execute(
                    "UPDATE village_resources SET diamonds = diamonds - 10 WHERE chat_id = ?",
                    (chat_id,),
                )
                cursor.execute(
                    "UPDATE players SET coins = coins + 50 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "💰 ۵۰ سکه با موفقیت خریداری شد!",
                    reply_markup=get_market_keyboard(),
                )
            else:
                conn.close()
                send_message(
                    chat_id,
                    "❌ الماس کافی در ذخایر روستا نداری! (نیاز به ۱۰ الماس)",
                    reply_markup=get_market_keyboard(),
                )

        elif text == "💎 خرید ۲۰ گوشت (۱۵ الماس)":
            cursor.execute(
                "SELECT diamonds FROM village_resources WHERE chat_id = ?",
                (chat_id,),
            )
            res = cursor.fetchone()
            v_diamonds = res[0] if res else 0

            if v_diamonds >= 15:
                cursor.execute(
                    "UPDATE village_resources SET diamonds = diamonds - 15 WHERE chat_id = ?",
                    (chat_id,),
                )
                cursor.execute(
                    "UPDATE players SET meat = meat + 20 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                conn.close()
                send_message(
                    chat_id,
                    "🥩 ۲۰ گوشت با موفقیت خریداری شد!",
                    reply_markup=get_market_keyboard(),
                )
            else:
                conn.close()
                send_message(
                    chat_id,
                    "❌ الماس کافی در ذخایر روستا نداری! (نیاز به ۱۵ الماس)",
                    reply_markup=get_market_keyboard(),
                )

        elif text == "⚔️ نبرد PvP":
            cursor.execute(
                "SELECT chat_id, name, power, soldiers FROM players WHERE chat_id != ?",
                (chat_id,),
            )
            targets = cursor.fetchall()
            conn.close()

            if not targets:
                send_message(
                    chat_id,
                    "🛡️ هنوز حاکم دیگری در بازی ثبت‌نام نکرده است. منتظر بمانید تا بازیکنان دیگر هم وارد شوند!",
                    reply_markup=get_main_keyboard(),
                )
                return

            target_keyboard = []
            for t_id, t_name, t_p, t_s in targets:
                t_total = t_p + (t_s * 5)
                target_keyboard.append(
                    [{"text": f"⚔️ حمله به {t_name} (قدرت: {t_total})"}]
                )
            target_keyboard.append([{"text": "🔙 بازگشت به منوی اصلی"}])

            send_message(
                chat_id,
                "⚔️ **انتخاب حریف برای نبرد:**\nکدام قلمرو را برای یورش انتخاب می‌کنید؟",
                reply_markup={
                    "keyboard": target_keyboard,
                    "resize_keyboard": True,
                },
            )

        elif text.startswith("⚔️ حمله به "):
            target_name_part = text.replace("⚔️ حمله به ", "").split(" (")[0]
            cursor.execute(
                "SELECT chat_id FROM players WHERE name = ? AND chat_id != ?",
                (target_name_part, chat_id),
            )
            target_row = cursor.fetchone()

            if not target_row:
                conn.close()
                send_message(
                    chat_id,
                    "❌ حریف یافت نشد یا منقضی شده است.",
                    reply_markup=get_main_keyboard(),
                )
                return

            target_id = target_row[0]
            cursor.execute(
                "UPDATE players SET state = ? WHERE chat_id = ?",
                (f"ATTACKING_{target_id}", chat_id),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                f"⚠️ آیا مطمئنی که می‌خواهی به **{target_name_part}** حمله کنی؟\n(برای تایید دوباره دکمه حمله را بزنید یا به منوی اصلی برگردید)",
                reply_markup=get_main_keyboard(),
            )

        elif text == "👥 اتحادها":
            conn.close()
            send_message(
                chat_id,
                "👥 **بخش اتحادها**\nمی‌توانید اتحاد بسازید یا مدیریت کنید.",
                reply_markup=get_clan_keyboard(clan_id > 0),
            )

        elif text == "🏗️ ساخت اتحاد جدید":
            cursor.execute(
                "UPDATE players SET state = 'WAITING_CLAN_NAME' WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                "📝 لطفاً نام اتحاد جدید خود را وارد کنید:",
                reply_markup={
                    "keyboard": [[{"text": "🔙 بازگشت به منوی اصلی"}]],
                    "resize_keyboard": True,
                },
            )

        elif text == "👥 اعضای اتحاد":
            if clan_id == 0:
                conn.close()
                send_message(chat_id, "❌ شما عضو هیچ اتحادی نیستید!")
                return
            cursor.execute(
                "SELECT name, power FROM players WHERE clan_id = ?", (clan_id,)
            )
            members = cursor.fetchall()
            conn.close()

            member_list = "👥 **اعضای اتحاد:**\n\n"
            for m_name, m_power in members:
                member_list += f"- {m_name} (قدرت: {m_power})\n"
            send_message(
                chat_id, member_list, reply_markup=get_clan_keyboard(True)
            )

        elif text == "🚪 ترک اتحاد":
            cursor.execute(
                "UPDATE players SET clan_id = 0 WHERE chat_id = ?", (chat_id,),
            )
            conn.commit()
            conn.close()
            send_message(
                chat_id,
                "🚪 شما از اتحاد خارج شدید.",
                reply_markup=get_clan_keyboard(False),
            )

        elif text == "📜 راهنما":
            conn.close()
            guide = (
                "📜 **راهنمای بازی حاکم قلمرو**\n\n"
                "1. با ساخت کارخانه‌ها و قصابی‌ها منابع کسب کنید.\n"
                "2. سرباز تربیت کنید تا قدرت نظامی‌تان بالا برود.\n"
                "3. با دیگر حاکمان بجنگید و غنایم بگیرید.\n"
                "4. اتحاد تشکیل دهید و قدرتمندتر شوید!"
            )
            send_message(chat_id, guide, reply_markup=get_main_keyboard())

        else:
            conn.close()
            send_message(
                chat_id,
                "دستور نامعتبر است. از منوی زیر استفاده کنید:",
                reply_markup=get_main_keyboard(),
            )


# حلقه دریافت آپدیت‌ها از بله (Long Polling)
def handle_updates():
    offset = 0
    print("Bot polling started...")
    while True:
        try:
            url = f"{BASE_URL}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            if response.status_code == 200:
                data = response.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    if "message" in update:
                        threading.Thread(
                            target=handle_message, args=(update["message"],)
                        ).start()
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    # استارت ترد تولید منابع
    threading.Thread(target=resource_production_loop, daemon=True).start()

    # استارت ترد پینگ خودکار
    threading.Thread(target=self_ping, daemon=True).start()

    # استارت سرور وب فلشک در یک ترد جداگانه برای رندر
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port), daemon=True
    ).start()

    # اجرای حلقه اصلی دریافت پیام‌ها در ترد اصلی
    handle_updates()
