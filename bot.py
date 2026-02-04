import sqlite3
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ =================

import os
TOKEN = os.getenv("TOKEN")

ALLOWED_USERS = [
    505720213,
    935696258
]

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================= БАЗА =================

conn = sqlite3.connect("shifts.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    rate REAL,
    consum REAL,
    tips REAL,
    user_id INTEGER
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


# ================= START =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    if message.from_user.id not in ALLOWED_USERS:
        return

    await message.answer(
        "💎 <b>Shift Manager</b>\n\nВыбери действие:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )

    await message.answer(
        "👇 Меню:",
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

    if message.from_user.id not in ALLOWED_USERS:
        return

    try:
        date, rate, consum, tips = message.text.split()

        cursor.execute(
            "INSERT INTO shifts (date, rate, consum, tips, user_id) VALUES (?, ?, ?, ?, ?)",
            (date, rate, consum, tips, message.from_user.id)
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

    cursor.execute(
        "SELECT date, rate, consum, tips FROM shifts WHERE user_id = ?",
        (callback.from_user.id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await callback.message.answer("Нет данных")
        return

    shifts = len(rows)
    total = sum(float(r[1]) + float(r[2]) + float(r[3]) for r in rows)
    avg = total / shifts

    best = max(rows, key=lambda r: float(r[1]) + float(r[2]) + float(r[3]))
    best_total = float(best[1]) + float(best[2]) + float(best[3])

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

    cursor.execute("""
        SELECT id, date, rate, consum, tips
        FROM shifts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (callback.from_user.id,))

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

    cursor.execute("""
        SELECT id, date, rate, consum, tips
        FROM shifts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (callback.from_user.id,))

    rows = cursor.fetchall()

    if not rows:
        await callback.message.edit_text(
            "Нет смен для удаления",
            reply_markup=inline_main_menu()
        )
        return

    kb = InlineKeyboardMarkup(row_width=1)

    text = "🗑 Выбери смену для удаления:\n\n"

    for r in rows:
        total = r[2] + r[3] + r[4]
        text += f"{r[0]}. {r[1]} — {total:.2f}\n"

        kb.add(
            InlineKeyboardButton(
                f"❌ Удалить {r[1]}",
                callback_data=f"del_{r[0]}"
            )
        )

    kb.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()
    await callback.message.answer("Напиши:\n/delete НОМЕР")
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
    await callback.message.edit_text(
        "💎 <b>Shift Manager</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

@dp.message_handler(commands=["delete"])
async def delete_shift(message: types.Message):

    args = message.get_args()

    if not args.isdigit():
        await message.answer("Используй:\n/delete НОМЕР")
        return

    cursor.execute(
        "DELETE FROM shifts WHERE id = ? AND user_id = ?",
        (int(args), message.from_user.id)
    )
    conn.commit()

    await message.answer("🗑 Удалено", reply_markup=inline_main_menu())


# ================= МЕСЯЦ =================

@dp.callback_query_handler(lambda c: c.data == "month")
async def month_stats(callback: types.CallbackQuery):
    await callback.answer()

    month = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT rate, consum, tips
        FROM shifts
        WHERE user_id = ? AND date LIKE ?
    """, (callback.from_user.id, f"{month}%"))

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


# ================= НАПОМИНАНИЕ В 08:00 =================

async def check_shifts():

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for user_id in ALLOWED_USERS:

        cursor.execute("""
            SELECT * FROM shifts
            WHERE user_id = ? AND date = ?
        """, (user_id, yesterday))

        row = cursor.fetchone()

        if not row:
            await bot.send_message(
                user_id,
                f"🌙 Ты не внёс смену за {yesterday}\n\n"
                f"Смена закончилась — не забудь внести данные 👇",
                reply_markup=inline_main_menu()
            )


# ================= ЗАПУСК =================

async def on_startup(dp):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_shifts, "cron", hour=8, minute=0)
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)