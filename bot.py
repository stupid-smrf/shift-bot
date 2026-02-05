import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os

# ================= НАСТРОЙКИ =================

TOKEN = os.getenv("TOKEN")

ALLOWED_USERS = [
    505720213,
    935696258
]

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
pending_updates = {}

# ================= БАЗА =================

conn = sqlite3.connect("shifts.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    rate REAL,
    consum REAL,
    tips REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    registered_at TEXT
)
""")

conn.commit()
# ================= РЕГИСТРАЦИЯ =================

def register_user(user: types.User):
    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user.id,)
    )
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(
            "INSERT INTO users (user_id, first_name, username, registered_at) VALUES (?, ?, ?, ?)",
            (
                user.id,
                user.first_name,
                user.username,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        conn.commit()

# ================= МЕНЮ =================

def inline_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Общая статистика", callback_data="stats"),
        InlineKeyboardButton("📋 Последние", callback_data="list"),
        InlineKeyboardButton("➕ Добавить", callback_data="add"),
        InlineKeyboardButton("🗑 Удалить", callback_data="delete"),
        InlineKeyboardButton("📅 Текущий месяц", callback_data="month"),
        InlineKeyboardButton("🗂 Выбрать месяц", callback_data="choose_month"),
        InlineKeyboardButton("🔥 Лучший месяц", callback_data="best_month"),
    )
    return kb


import random

def build_main_screen(user_id):
    today = datetime.now().strftime("%d.%m.%Y")
    today_db = datetime.now().strftime("%Y-%m-%d")
    month_name = datetime.now().strftime("%B")

    # Получаем смены пользователя
    cursor.execute("""
        SELECT date, rate, consum, tips
        FROM shifts
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()

    shifts_count = len(rows)

    total_rate = sum(r[1] for r in rows) if rows else 0
    total_consum = sum(r[2] for r in rows) if rows else 0
    total_tips = sum(r[3] for r in rows) if rows else 0
    total_income = total_rate + total_consum + total_tips
    avg_income = total_income / shifts_count if shifts_count else 0

    # Проверка внесена ли смена сегодня
    cursor.execute("""
        SELECT 1 FROM shifts
        WHERE user_id = ? AND date = ?
    """, (user_id, today_db))
    today_exists = cursor.fetchone()

    status = "✅ Внесена" if today_exists else "❌ Не внесена"

    # Мотивационные фразы
    quotes = [
    "Дисциплина делает деньги",
    "Система > мотивация",
    "Каждая смена — шаг к свободе",
    "Стабильность — это сила",
    "Работаешь умно — живёшь красиво",

    "Сегодня тяжело — завтра дорого",
    "Большие цифры любят порядок",
    "Контроль = рост",
    "Деньги любят учет",
    "Каждый вечер — инвестиция в себя",

    "Не настроение решает, а система",
    "Маленькие шаги → большие суммы",
    "Фокус на цифрах = фокус на результате",
    "Ты управляешь деньгами, а не наоборот",
    "Тот, кто считает — тот зарабатывает",

    "Смена за сменой — строится свобода",
    "Финансовая дисциплина — новый уровень",
    "Работаешь ночью — строишь будущее",
    "Сильные люди фиксируют результат",
    "Ты уже делаешь больше, чем вчера",

    "Рост начинается с учета",
    "Каждая внесенная смена — победа",
    "Статистика не врет",
    "Сначала учет — потом масштаб",
    "PRO начинается с порядка",

    "Твой доход — отражение твоей системы",
    "Цифры — это сила",
    "Тихая дисциплина = громкие результаты",
    "Регулярность делает богатым",
    "Система решает всё"
]

    quote = random.choice(quotes)

    text = (
        "💎 <b>Твой личный менеджер по доходу 💅</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>{today}</b> | {month_name}\n\n"
        "📊 <b>Общая статистика</b>\n"
        f"Смен: <b>{shifts_count}</b>\n"
        f"💰 Доход: <b>{total_income:.2f}</b>\n"
        f"📈 Средний: <b>{avg_income:.2f}</b>\n\n"
        "🗓 <b>Сегодняшняя смена</b>\n"
        f"{status}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 <i>{quote}</i>\n\n"
        "👇 Выбери действие:"
    )
    return text
# ================= START =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):

    register_user(message.from_user)

    text = build_main_screen(message.from_user.id)

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )
@dp.message_handler(commands=["stats"])
async def stats_command(message: types.Message):
    user_id = message.from_user.id

    cursor.execute(
        "SELECT date, rate, consum, tips FROM shifts WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await message.answer("Нет данных")
        return

    shifts = len(rows)
    total_rate = sum(r[1] for r in rows)
    total_consum = sum(r[2] for r in rows)
    total_tips = sum(r[3] for r in rows)

    total = total_rate + total_consum + total_tips
    avg = total / shifts

    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📅 Смен: <b>{shifts}</b>\n\n"
        f"💵 Ставка: <b>{total_rate:.2f}</b>\n"
        f"🍾 Консум: <b>{total_consum:.2f}</b>\n"
        f"☕ Чай: <b>{total_tips:.2f}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Итого: <b>{total:.2f}</b>\n"
        f"📈 Средний: <b>{avg:.2f}</b>",
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )
    @dp.message_handler(commands=["add"])
    async def add_command(message: types.Message):
     await message.answer(
        "📅 Формат:\n\n"
        "ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "2026-02-01 100 80 40"
    )
     @dp.message_handler(commands=["list"])
     async def list_command(message: types.Message):
      user_id = message.from_user.id

    cursor.execute("""
        SELECT id, date, rate, consum, tips
        FROM shifts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (user_id,))

    rows = cursor.fetchall()

    if not rows:
        await message.answer("Нет данных")
        return

    text = "📋 <b>Последние смены</b>\n\n"
    for r in rows:
        total = r[2] + r[3] + r[4]
        text += f"{r[0]}. {r[1]} — {total:.2f}\n"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )
# ================= ДОБАВИТЬ =================

@dp.callback_query_handler(lambda c: c.data == "add")
async def add_shift(callback: types.CallbackQuery):
    await callback.answer()

    await callback.message.answer(
        "━━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>Добавление смены</b>\n\n"
        "Формат:\n"
        "ГГГГ-ММ-ДД СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "2026-02-01 100 80 40\n\n"
        "Где:\n"
        "💰 Ставка\n"
        "🍾 Консум\n"
        "☕ Чай",
        parse_mode="HTML"
    )


@dp.message_handler(lambda m: m.text and not m.text.startswith("/"))
async def save_shift(message: types.Message):

    if message.from_user.id not in ALLOWED_USERS:
        return

    try:
        parts = message.text.split()
        user_id = message.from_user.id

        today = datetime.now()
        current_year = today.year

        # -------------------------------
        # Определяем дату
        # -------------------------------
        if len(parts) == 3:
            date = today.strftime("%Y-%m-%d")
            rate, consum, tips = parts

        elif parts[0].lower() == "вчера" and len(parts) == 4:
            date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            rate, consum, tips = parts[1:]

        elif "." in parts[0] and len(parts) == 4:
            day, month = parts[0].split(".")
            date_obj = datetime(current_year, int(month), int(day))
            date = date_obj.strftime("%Y-%m-%d")
            rate, consum, tips = parts[1:]

        elif len(parts) == 4 and "-" in parts[0]:
            date, rate, consum, tips = parts

        else:
            await message.answer("❌ Неверный формат")
            return

        # -------------------------------
        # Проверка на дубль
        # -------------------------------
        cursor.execute(
            "SELECT id FROM shifts WHERE user_id = ? AND date = ?",
            (user_id, date)
        )
        existing = cursor.fetchone()

        if existing:
            pending_updates[user_id] = {
                "date": date,
                "rate": float(rate),
                "consum": float(consum),
                "tips": float(tips)
            }

            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("✏️ Обновить", callback_data="confirm_update"))
            kb.add(InlineKeyboardButton("❌ Отмена", callback_data="back"))

            await message.answer(
                f"⚠️ Смена за {date} уже существует.\n\nОбновить её?",
                reply_markup=kb
            )
            return

        # -------------------------------
        # Сохраняем новую
        # -------------------------------
        cursor.execute(
            "INSERT INTO shifts (user_id, date, rate, consum, tips) VALUES (?, ?, ?, ?, ?)",
            (user_id, date, float(rate), float(consum), float(tips))
        )
        conn.commit()

        text = build_main_screen(user_id)

        await message.answer(
            "✅ Смена сохранена\n\n" + text,
            parse_mode="HTML",
            reply_markup=inline_main_menu()
        )

    except:
        await message.answer("❌ Ошибка формата или даты")
@dp.callback_query_handler(lambda c: c.data == "confirm_update")
async def confirm_update(callback: types.CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    if user_id not in pending_updates:
        return

    data = pending_updates[user_id]

    cursor.execute("""
        UPDATE shifts
        SET rate = ?, consum = ?, tips = ?
        WHERE user_id = ? AND date = ?
    """, (
        data["rate"],
        data["consum"],
        data["tips"],
        user_id,
        data["date"]
    ))

    conn.commit()

    del pending_updates[user_id]

    text = build_main_screen(user_id)

    await callback.message.edit_text(
        "✏️ Смена обновлена\n\n" + text,
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

# ================= СТАТИСТИКА =================

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    cursor.execute(
        "SELECT date, rate, consum, tips FROM shifts WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer("Нет данных")
        return

    shifts = len(rows)
    total_rate = sum(r[1] for r in rows)
    total_consum = sum(r[2] for r in rows)
    total_tips = sum(r[3] for r in rows)

    total = total_rate + total_consum + total_tips
    avg = total / shifts
    best = max(rows, key=lambda r: r[1] + r[2] + r[3])
    best_total = best[1] + best[2] + best[3]

    await callback.message.answer(
    f"📊 <b>Твоя статистика</b>\n\n"
    f"📅 Смен: <b>{len(rows)}</b>\n\n"
    f"💵 Ставка: <b>{total_rate:.2f}</b>\n"
    f"🍾 Консум: <b>{total_consum:.2f}</b>\n"
    f"☕ Чай: <b>{total_tips:.2f}</b>\n"
    f"━━━━━━━━━━━━━━\n"
    f"💰 Итого: <b>{total:.2f}</b>\n"
    f"📈 Средний: <b>{avg:.2f}</b>",
    parse_mode="HTML",
    reply_markup=inline_main_menu()
)

# ================= ПОСЛЕДНИЕ =================

@dp.callback_query_handler(lambda c: c.data == "list")
async def list_shifts(callback: types.CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    cursor.execute("""
        SELECT id, date, rate, consum, tips
        FROM shifts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (user_id,))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer("Нет данных")
        return

    text = "📋 <b>Последние смены</b>\n\n"
    for r in rows:
        total = r[2] + r[3] + r[4]
        text += f"{r[0]}. {r[1]} — {total:.2f}\n"

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

# ================= УДАЛЕНИЕ =================

@dp.callback_query_handler(lambda c: c.data == "delete")
async def delete_menu(callback: types.CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    cursor.execute("""
        SELECT id, date
        FROM shifts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (user_id,))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer("Нет смен для удаления")
        return

    kb = InlineKeyboardMarkup(row_width=1)

    for r in rows:
        kb.add(
            InlineKeyboardButton(
                f"❌ Удалить {r[1]}",
                callback_data=f"del_{r[0]}"
            )
        )

    kb.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))

    await callback.message.answer("Выбери смену:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data.startswith("del_"))
async def delete_shift_callback(callback: types.CallbackQuery):
    await callback.answer()

    shift_id = int(callback.data.split("_")[1])

    cursor.execute(
        "DELETE FROM shifts WHERE id = ? AND user_id = ?",
        (shift_id, callback.from_user.id)
    )
    conn.commit()

    text = build_main_screen(callback.from_user.id)

    await callback.message.edit_text(
        "✅ Смена удалена\n\n" + text,
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )


@dp.callback_query_handler(lambda c: c.data == "back")
async def go_back(callback: types.CallbackQuery):
    await callback.answer()

    text = build_main_screen(callback.from_user.id)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

# ================= МЕСЯЦ =================

@dp.callback_query_handler(lambda c: c.data == "month")
async def month_stats(callback: types.CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id
    month = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT rate, consum, tips
        FROM shifts
        WHERE user_id = ? AND date LIKE ?
    """, (user_id, f"{month}%"))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer("Нет данных за месяц")
        return

    shifts = len(rows)

    total_rate = sum(r[0] for r in rows)
    total_consum = sum(r[1] for r in rows)
    total_tips = sum(r[2] for r in rows)

    total = total_rate + total_consum + total_tips
    avg = total / shifts

    await callback.message.answer(
    f"📅 <b>Статистика за {month}</b>\n\n"
    f"📅 Смен: <b>{shifts}</b>\n\n"
    f"💵 Ставка: <b>{total_rate:.2f}</b>\n"
    f"🍾 Консум: <b>{total_consum:.2f}</b>\n"
    f"☕ Чай: <b>{total_tips:.2f}</b>\n"
    f"━━━━━━━━━━━━━━\n"
    f"💰 Итого: <b>{total:.2f}</b>\n"
    f"📈 Средний: <b>{avg:.2f}</b>",
    parse_mode="HTML",
    reply_markup=inline_main_menu()
)
@dp.callback_query_handler(lambda c: c.data == "best_month")
async def best_month(callback: types.CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id

    cursor.execute("""
        SELECT substr(date, 1, 7) as month,
               SUM(rate + consum + tips) as total
        FROM shifts
        WHERE user_id = ?
        GROUP BY month
        ORDER BY total DESC
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()

    if not row:
        await callback.message.answer("Нет данных")
        return

    month, total = row

    await callback.message.answer(
        f"🔥 <b>Лучший месяц</b>\n\n"
        f"📅 {month}\n"
        f"💰 Доход: <b>{total:.2f}</b>",
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )
@dp.callback_query_handler(lambda c: c.data == "choose_month")
async def choose_month(callback: types.CallbackQuery):
    await callback.answer()

    await callback.message.answer(
        "📅 Введи месяц в формате:\n\n"
        "ГГГГ-ММ\n\n"
        "Пример:\n"
        "2026-02"
    )
@dp.message_handler(lambda m: len(m.text) == 7 and "-" in m.text)
async def custom_month_stats(message: types.Message):

    user_id = message.from_user.id
    month = message.text

    cursor.execute("""
        SELECT rate, consum, tips
        FROM shifts
        WHERE user_id = ? AND date LIKE ?
    """, (user_id, f"{month}%"))

    rows = cursor.fetchall()

    if not rows:
        await message.answer("Нет данных за этот месяц")
        return

    shifts = len(rows)
    total = sum(r[0] + r[1] + r[2] for r in rows)
    avg = total / shifts

    await message.answer(
        f"📅 <b>Статистика за {month}</b>\n\n"
        f"📅 Смен: <b>{shifts}</b>\n"
        f"💰 Итого: <b>{total:.2f}</b>\n"
        f"📈 Средний: <b>{avg:.2f}</b>",
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )
    # ================= СЕГОДНЯ =================
@dp.callback_query_handler(lambda c: c.data == "today")
async def today_shift(callback: types.CallbackQuery):
    await callback.answer()

    await callback.message.answer(
        "📅 <b>Сегодняшняя смена</b>\n\n"
        "Введи:\n\n"
        "СТАВКА КОНСУМ ЧАЙ\n\n"
        "Пример:\n"
        "3000 2300 2500",
        parse_mode="HTML"
    )

# ================= НАПОМИНАНИЕ =================

async def check_shifts():

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for user_id in ALLOWED_USERS:
        cursor.execute("""
            SELECT 1 FROM shifts
            WHERE user_id = ? AND date = ?
        """, (user_id, yesterday))

        row = cursor.fetchone()

        if not row:
            await bot.send_message(
                user_id,
                f"🌙 Ты не внёс смену за {yesterday}\n\nНе забудь добавить 👇",
                reply_markup=inline_main_menu()
            )

# ================= ЗАПУСК =================

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_shifts, "cron", hour=8, minute=0)
    scheduler.start()

    await set_commands(dp)

async def set_commands(dp):
    await bot.set_my_commands([
        types.BotCommand("start", "Главное меню"),
        types.BotCommand("add", "Добавить смену"),
        types.BotCommand("stats", "Общая статистика"),
        types.BotCommand("month", "Статистика за месяц"),
        types.BotCommand("list", "Последние смены"),
        types.BotCommand("delete", "Удалить смену"),
        types.BotCommand("help", "Помощь"),
    ])
if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)