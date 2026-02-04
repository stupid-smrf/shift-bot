import sqlite3
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ =================

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

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
conn.commit()

# ================= МЕНЮ =================

def inline_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("📋 Последние", callback_data="list"),
        InlineKeyboardButton("➕ Добавить", callback_data="add"),
        InlineKeyboardButton("🗑 Удалить", callback_data="delete"),
        InlineKeyboardButton("📅 Месяц", callback_data="month"),
    )
    return kb
def build_main_screen(user_id):
    today = datetime.now().strftime("%Y-%m-%d")

    # Получаем все смены пользователя
    cursor.execute("""
        SELECT date, rate, consum, tips
        FROM shifts
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()

    shifts_count = len(rows)

    total_income = sum(float(r[1]) + float(r[2]) + float(r[3]) for r in rows) if rows else 0
    avg_income = total_income / shifts_count if shifts_count else 0

    # Проверка внесена ли смена сегодня
    cursor.execute("""
        SELECT 1 FROM shifts
        WHERE user_id = ? AND date = ?
    """, (user_id, today))
    today_exists = cursor.fetchone()

    status = "✅ Внесена" if today_exists else "❌ Не внесена"

    text = (
        "💎 <b>Shift Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Сегодня: <b>{today}</b>\n\n"
        "📊 <b>Общая статистика</b>\n"
        f"Смен: <b>{shifts_count}</b>\n"
        f"💰 Доход: <b>{total_income:.2f}</b>\n"
        f"📈 Средний: <b>{avg_income:.2f}</b>\n\n"
        "🗓 <b>Сегодняшняя смена</b>\n"
        f"{status}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👇 Выбери действие:"
    )

    return text

# ================= START =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    if message.from_user.id not in ALLOWED_USERS:
        return

    text = build_main_screen(message.from_user.id)

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

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
        "Введи данные в формате:\n\n"
        "📅 ГГГГ-ММ-ДД 💰 СТАВКА 🍾 КОНСУМ ☕ ЧАЙ\n\n"
        "Пример:\n"
        "2026-02-01 100 80 40\n\n"
        "Где:\n"
        "💰 100 — ставка\n"
        "🍾 80 — консум\n"
        "☕ 40 — чай"
    )


@dp.message_handler(lambda m: m.text and len(m.text.split()) == 4)
async def save_shift(message: types.Message):

    try:
        date, rate, consum, tips = message.text.split()

        user_id = message.from_user.id

        cursor.execute(
            "INSERT INTO shifts (user_id, date, rate, consum, tips) VALUES (?, ?, ?, ?, ?)",
            (user_id, date, float(rate), float(consum), float(tips))
        )
        conn.commit()

        await message.answer(
            "✅ Смена сохранена",
            reply_markup=inline_main_menu()
        )

    except:
        await message.answer("❌ Ошибка формата")


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
    total = sum(r[1] + r[2] + r[3] for r in rows)
    avg = total / shifts

    best = max(rows, key=lambda r: r[1] + r[2] + r[3])
    best_total = best[1] + best[2] + best[3]

    await callback.message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📅 Смен: <b>{shifts}</b>\n"
        f"💰 Общий доход: <b>{total:.2f}</b>\n"
        f"📈 Средний: <b>{avg:.2f}</b>\n\n"
        f"🔥 Лучшая смена: {best[0]} — <b>{best_total:.2f}</b>",
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

    text = "📋 Последние смены:\n\n"
    for r in rows:
        total = r[2] + r[3] + r[4]
        text += f"{r[0]}. {r[1]} — {total:.2f}\n"

    await callback.message.answer(text, reply_markup=inline_main_menu())


# ================= УДАЛЕНИЕ =================

@dp.callback_query_handler(lambda c: c.data == "delete")
async def delete_menu(callback: types.CallbackQuery):
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

    await callback.message.edit_text(
        "✅ Смена удалена",
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
    total = sum(r[0] + r[1] + r[2] for r in rows)
    avg = total / shifts

    await callback.message.answer(
        f"📅 {month}\n\n"
        f"Смен: {shifts}\n"
        f"💰 Общий: {total:.2f}\n"
        f"📈 Средний: {avg:.2f}",
        reply_markup=inline_main_menu()
    )


# ================= НАПОМИНАНИЕ =================

async def check_shifts():

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    cursor.execute("SELECT DISTINCT user_id FROM shifts")
    users = cursor.fetchall()

    for (user_id,) in users:

        cursor.execute("""
            SELECT * FROM shifts
            WHERE user_id = ? AND date = ?
        """, (user_id, yesterday))

        row = cursor.fetchone()

        if not row:
            await bot.send_message(
                user_id,
                f"🌙 Ты не внёс смену за {yesterday}\n\n"
                f"Не забудь добавить 👇",
                reply_markup=inline_main_menu()
            )


# ================= ЗАПУСК =================

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_shifts, "cron", hour=8, minute=0)
    scheduler.start()


if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)