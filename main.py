import os
import asyncio
import logging
import json
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

# ==================== ASOSIY SOZLAMALAR ====================
BOT_TOKEN = "8736913988:AAEt_b45vOcUE-VwVFY_R1hM0Vv0TvXhtCg"
MAIN_ADMIN_ID = 6526733680
DEFAULT_CHANNEL_TAG = "@AniFible"
PORT = int(os.getenv("PORT", 10000))
DB_NAME = "anime_data.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== BAZA (SQLITE) ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            code TEXT PRIMARY KEY,
            title TEXT,
            poster TEXT,
            description TEXT,
            episodes TEXT
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT
        )
    """)
    conn.commit()
    conn.close()

def db_is_admin(user_id: int) -> bool:
    if user_id == MAIN_ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return bool(res)

def db_add_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def db_get_channels():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT channel_id, title, url FROM channels")
    rows = cur.fetchall()
    conn.close()
    return rows

# ==================== OBUNA TEKSHIRISH ====================
async def check_user_subscriptions(user_id: int):
    channels = db_get_channels()
    unsubscribed = []
    for ch_id, title, url in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                unsubscribed.append((title, url))
        except Exception:
            continue
    return unsubscribed

def get_sub_keyboard(unsubscribed_channels, code_to_resume=None):
    keyboard = []
    for title, url in unsubscribed_channels:
        keyboard.append([InlineKeyboardButton(text=f"➕ {title}", url=url)])
    cb_data = f"check_sub_{code_to_resume}" if code_to_resume else "check_sub"
    keyboard.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data=cb_data)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ==================== TUGMALAR ====================
def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Anime qoʻshish")],
            [KeyboardButton(text="📢 Majburiy kanal"), KeyboardButton(text="👥 Admin qoʻshish/oʻchirish")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="✉️ Xabar yuborish")],
            [KeyboardButton(text="📋 Animelar roʻyxati"), KeyboardButton(text="🗑 Animeni oʻchirish")]
        ],
        resize_keyboard=True
    )

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

# ==================== FSM BOSQICHLARI ====================
class AnimeProcess(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_poster = State()
    waiting_for_desc = State()
    waiting_for_videos = State()
    edit_desc = State()

class ChannelManage(StatesGroup):
    waiting_for_data = State()

class AdminManage(StatesGroup):
    waiting_for_id = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class SingleDelete(StatesGroup):
    waiting_for_code = State()

# ==================== BEKOR QILISH ====================
@dp.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Jarayon bekor qilindi. Bosh menyudasiz:", reply_markup=get_admin_keyboard())

# ==================== ADMIN PANEL /admin ====================
@dp.message(Command("admin"))
async def admin_cmd_handler(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return await message.answer("Siz admin emassiz.")
    await state.clear()
    user_mention = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
    await message.answer(
        f"👋 Assalomu alaykum, {user_mention}!\n\n"
        f"🛠 <b>Siz uchun Boshqaruv Menyusi faol:</b>",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )

# ==================== 1. ANIME QO'SHISH ====================
@dp.message(F.text == "🎬 Anime qoʻshish")
async def add_anime_start(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.set_state(AnimeProcess.waiting_for_code)
    await message.answer("Anime kodini kiriting (masalan: <b>2</b>):", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AnimeProcess.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    code = message.text.strip()
    await state.update_data(code=code, episodes=[])
    await state.set_state(AnimeProcess.waiting_for_title)
    await message.answer(
        "Anime nomi va faslini kiriting:\n(Masalan: <b>Yetti o'lim gunohi [1-fasl]</b>)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(AnimeProcess.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AnimeProcess.waiting_for_poster)
    await message.answer("Anime uchun <b>poster</b> tashlang (rasm):", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AnimeProcess.waiting_for_poster, F.photo)
async def process_poster(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    poster_id = message.photo[-1].file_id
    await state.update_data(poster=poster_id)
    await state.set_state(AnimeProcess.waiting_for_desc)
    
    example_desc = (
        "O'yinchoqlar Tarixi\n"
        "╭──────────────────────\n"
        "├‣  Qism: 5Ta Film\n"
        "├‣  Holati: Tugallangan \n"
        "├‣  Sifat - 720p, 1080p\n"
        "├‣  Janrlari: Fantasy, Sarguzasht\n"
        f"├‣  Kanal: {DEFAULT_CHANNEL_TAG}\n"
        "╰──────────────────────"
    )
    await message.answer(
        f"Endi anime uchun <b>tavsif (izoh)</b> yuboring.\nMasalan quyidagicha nusxalab tahrirlashingiz mumkin:\n\n"
        f"<code>{example_desc}</code>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(AnimeProcess.waiting_for_desc)
async def process_desc(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    desc = message.text.strip()
    await state.update_data(desc=desc)
    await state.set_state(AnimeProcess.waiting_for_videos)
    await message.answer(
        "Ajoyib! Endi animening barcha qismlarini (videolarni) ketma-ket tashlang.\n"
        "Har bir qism tagiga avtomatik nom va qism tartibi yoziladi.\n\n"
        "Barcha qismlar yuklangach, pastdagi <b>«✅ Yakunlandimi?»</b> tugmasini bosing.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(AnimeProcess.waiting_for_videos, F.video)
async def process_video_upload(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    episodes.append(message.video.file_id)
    await state.update_data(episodes=episodes)

    finish_inline = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yakunlandimi?", callback_data="anime_upload_finish")]
    ])
    await message.answer(
        f"✅ <b>{len(episodes)}-qism</b> qabul qilindi.\n"
        "Yana qismlar boʻlsa tashlayvering, bo'lgach tugmani bosing:",
        reply_markup=finish_inline,
        parse_mode="HTML"
    )

def get_anime_management_keyboard(code: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Kanalga post yuborilsinmi?", callback_data=f"send_ch_{code}")],
        [InlineKeyboardButton(text="✏️ Izohni sozlaysizmi?", callback_data=f"edit_desc_{code}")],
        [InlineKeyboardButton(text="🗑 Animeni oʻchirasizmi?", callback_data=f"del_curr_{code}")]
    ])

@dp.callback_query(F.data == "anime_upload_finish")
async def finish_upload_flow(call: types.CallbackQuery, state: FSMContext):
    if not db_is_admin(call.from_user.id):
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    if not episodes:
        return await call.answer("Hech qanday video yuklanmadi!", show_alert=True)

    code = data["code"]
    title = data["title"]
    poster = data["poster"]
    desc = data["desc"]

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO animes (code, title, poster, description, episodes)
        VALUES (?, ?, ?, ?, ?)
    """, (code, title, poster, desc, json.dumps(episodes)))
    conn.commit()
    conn.close()

    await call.message.delete()
    await call.message.answer(
        f"✅ <b>Anime muvaffaqiyatli saqlandi!</b>\n\n"
        f"🔢 Kodi: <b>{code}</b>\n"
        f"🏷 Nomi: <b>{title}</b>\n"
        f"🎞 Jami qismlar: <b>{len(episodes)} ta</b>\n"
        f"📝 Izoh:\n{desc}\n\n"
        f"Quyidagi amallardan birini tanlang:",
        reply_markup=get_anime_management_keyboard(code),
        parse_mode="HTML"
    )
    await state.clear()
    await call.message.answer("Bosh menyudasiz:", reply_markup=get_admin_keyboard())

# --- Kanalga post, izohni tahrirlash va o'chirish ---
@dp.callback_query(F.data.startswith("send_ch_"))
async def send_to_channel_cb(call: types.CallbackQuery):
    if not db_is_admin(call.from_user.id):
        return
    code = call.data.replace("send_ch_", "")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT title, poster, description, episodes FROM animes WHERE code = ?", (code,))
    row = cur.fetchone()
    cur.execute("SELECT channel_id FROM channels LIMIT 1")
    ch_row = cur.fetchone()
    conn.close()

    if not row:
        return await call.answer("Anime topilmadi!", show_alert=True)
    
    target_channel = ch_row[0] if ch_row else DEFAULT_CHANNEL_TAG
    title, poster, desc, eps_json = row
    total = len(json.loads(eps_json))
    bot_info = await bot.get_me()

    post_text = (
        f"🎬 <b>Yangi Anime Joylandi!</b>\n\n"
        f"🏷 <b>Nomi:</b> {title}\n"
        f"🔢 <b>Kodi:</b> <code>{code}</code>\n"
        f"🎞 <b>Qismlar:</b> {total} ta\n\n"
        f"📝 <b>Tavsif:</b>\n{desc}"
    )
    btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Tomosha qilish 🍿", url=f"https://t.me/{bot_info.username}?start={code}")]
    ])
    try:
        await bot.send_photo(chat_id=target_channel, photo=poster, caption=post_text, reply_markup=btn, parse_mode="HTML")
        await call.answer("✅ Kanalga post muvaffaqiyatli yuborildi!", show_alert=True)
    except Exception as e:
        await call.answer(f"❌ Xatolik: {e}\n(Bot kanalda admin ekanligini tekshiring)", show_alert=True)

@dp.callback_query(F.data.startswith("edit_desc_"))
async def edit_desc_prompt(call: types.CallbackQuery, state: FSMContext):
    if not db_is_admin(call.from_user.id):
        return
    code = call.data.replace("edit_desc_", "")
    await state.set_state(AnimeProcess.edit_desc)
    await state.update_data(edit_code=code)
    await call.message.answer(f"Kod <b>{code}</b> uchun yangi tavsif (izoh) yozing:", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AnimeProcess.edit_desc)
async def process_new_desc(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    data = await state.get_data()
    code = data.get("edit_code")
    new_desc = message.text.strip()

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE animes SET description = ? WHERE code = ?", (new_desc, code))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Kod <b>{code}</b> izohi yangilandi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_curr_"))
async def del_current_anime(call: types.CallbackQuery):
    if not db_is_admin(call.from_user.id):
        return
    code = call.data.replace("del_curr_", "")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM animes WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    await call.answer(f"✅ Kod {code} boʻlgan anime oʻchirildi!", show_alert=True)
    await call.message.delete()

# ==================== 2. MAJBURIY KANAL ====================
@dp.message(F.text == "📢 Majburiy kanal")
async def manage_channels(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    channels = db_get_channels()
    buttons = []
    text = "📢 <b>Majburiy obuna va anons kanallari:</b>\n\n"
    if channels:
        for ch_id, title, url in channels:
            buttons.append([
                InlineKeyboardButton(text=f"{title}", url=url),
                InlineKeyboardButton(text="❌ Oʻchirish", callback_data=f"del_ch_{ch_id}")
            ])
    else:
        text += f"Hozircha qo'shimcha kanal yo'q (standart kanal: {DEFAULT_CHANNEL_TAG}).\n"
    buttons.append([InlineKeyboardButton(text="➕ Kanal qoʻshish", callback_data="add_ch_btn")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data == "add_ch_btn")
async def add_channel_prompt(call: types.CallbackQuery, state: FSMContext):
    if not db_is_admin(call.from_user.id):
        return
    await state.set_state(ChannelManage.waiting_for_data)
    await call.message.answer(
        "Kanalni quyidagi formatda yuboring:\n\n"
        "<code>@KanalUsername|Kanal Nomi|https://t.me/KanalUsername</code>\n\n"
        "<i>Eslatma: Bot kanalda ADMIN boʻlishi kerak!</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(ChannelManage.waiting_for_data)
async def process_channel_input(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    try:
        parts = message.text.strip().split("|")
        ch_id = parts[0].strip()
        title = parts[1].strip()
        url = parts[2].strip()

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO channels (channel_id, title, url) VALUES (?, ?, ?)", (ch_id, title, url))
        conn.commit()
        conn.close()

        await state.clear()
        await message.answer(f"✅ <b>{title}</b> kanali muvaffaqiyatli qoʻshildi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")
    except Exception:
        await message.answer("❌ Notoʻgʻri format. Quyidagicha yuboring:\n<code>@KanalUsername|Kanal Nomi|https://t.me/KanalUsername</code>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_ch_"))
async def del_channel_cb(call: types.CallbackQuery):
    if not db_is_admin(call.from_user.id):
        return
    ch_id = call.data.replace("del_ch_", "")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()
    await call.answer("Kanal oʻchirildi!", show_alert=True)
    await call.message.delete()

# ==================== 3. ADMIN QO'SHISH/O'CHIRISH ====================
@dp.message(F.text == "👥 Admin qoʻshish/oʻchirish")
async def manage_admins(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return await message.answer("Faqat Bosh Admin boshqa adminlarni boshqara oladi.")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    admins = cur.fetchall()
    conn.close()

    text = f"👥 <b>Adminlar Roʻyxati:</b>\n\n👑 <b>Bosh Admin:</b> <code>{MAIN_ADMIN_ID}</code>\n"
    buttons = []
    for (adm_id,) in admins:
        buttons.append([
            InlineKeyboardButton(text=f"ID: {adm_id}", callback_data="none"),
            InlineKeyboardButton(text="❌ Oʻchirish", callback_data=f"del_adm_{adm_id}")
        ])
    buttons.append([InlineKeyboardButton(text="➕ Yangi Admin Qoʻshish", callback_data="add_adm_btn")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data == "add_adm_btn")
async def add_admin_call(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != MAIN_ADMIN_ID:
        return await call.answer("Faqat Bosh Admin qoʻsha oladi!", show_alert=True)
    await state.set_state(AdminManage.waiting_for_id)
    await call.message.answer("Yangi adminning <b>Telegram raqamli ID</b> sini yuboring:", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AdminManage.waiting_for_id)
async def process_admin_id(message: types.Message, state: FSMContext):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    text = message.text.strip()
    if not text.isdigit():
        return await message.answer("Faqat raqamlardan iborat ID yuboring.")
    new_id = int(text)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer(f"✅ ID <code>{new_id}</code> boʻlgan foydalanuvchi admin qilindi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_adm_"))
async def del_admin_call(call: types.CallbackQuery):
    if call.from_user.id != MAIN_ADMIN_ID:
        return
    adm_id = int(call.data.replace("del_adm_", ""))
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE user_id = ?", (adm_id,))
    conn.commit()
    conn.close()
    await call.answer("Admin oʻchirildi!", show_alert=True)
    await call.message.delete()

# ==================== 4. STATISTIKA ====================
@dp.message(F.text == "📊 Statistika")
async def stats_handler(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM animes")
    animes_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM channels")
    channels_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM admins")
    admins_cnt = cur.fetchone()[0] + 1
    conn.close()

    await message.answer(
        f"📊 <b>Bot Statistikasi:</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{users_cnt} ta</b>\n"
        f"🎬 Yuklangan animelar: <b>{animes_cnt} ta</b>\n"
        f"📢 Kanallar: <b>{channels_cnt} ta</b>\n"
        f"👥 Adminlar: <b>{admins_cnt} ta</b>",
        parse_mode="HTML"
    )

# ==================== 5. XABAR YUBORISH ====================
@dp.message(F.text == "✉️️ Xabar yuborish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni (matn, rasm yoki video) yuboring:", reply_markup=get_cancel_keyboard())

@dp.message(BroadcastState.waiting_for_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    conn.close()

    sent = 0
    failed = 0
    wait_msg = await message.answer("⏳ Xabar tarqatilmoqda...")

    for (uid,) in users:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await state.clear()
    await wait_msg.delete()
    await message.answer(
        f"✅ <b>Xabar tarqatish yakunlandi:</b>\n\n"
        f"Yuborildi: <b>{sent} ta</b>\n"
        f"Yetib bormadi: <b>{failed} ta</b>",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )

# ==================== 6. ANIMELAR RO'YXATI VA O'CHIRISH ====================
@dp.message(F.text == "📋 Animelar roʻyxati")
async def list_animes(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT code, title, episodes FROM animes")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return await message.answer("Bazada hali birorta ham anime yoʻq.")

    text = "📋 <b>Mavjud Animelar:</b>\n\n"
    for code, title, eps_json in rows:
        total = len(json.loads(eps_json))
        text += f"• Kodi: <code>{code}</code> | <b>{title}</b> ({total} qism)\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🗑 Animeni oʻchirish")
async def single_del_start(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.set_state(SingleDelete.waiting_for_code)
    await message.answer("Oʻchirmoqchi boʻlgan anime kodini yuboring:", reply_markup=get_cancel_keyboard())

@dp.message(SingleDelete.waiting_for_code)
async def process_single_del(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    code = message.text.strip()
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM animes WHERE code = ?", (code,))
    changes = conn.total_changes
    conn.commit()
    conn.close()

    await state.clear()
    if changes > 0:
        await message.answer(f"✅ Kod <code>{code}</code> boʻlgan anime oʻchirildi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")
    else:
        await message.answer("❌ Bunday kodli anime topilmadi.", reply_markup=get_admin_keyboard())

# ==================== QISMLARNI YUBORISH (TAGIDA AVTO MATN BILAN) ====================
async def deliver_anime(chat_id: int, code: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT title, episodes FROM animes WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return await bot.send_message(chat_id, "❌ Bunday kodli anime topilmadi. Kodni tekshirib qayta yuboring.")

    title, episodes_json = row
    episodes = json.loads(episodes_json)
    await bot.send_message(chat_id, f"🎬 <b>{title}</b> barcha qismlari yuklanmoqda...", parse_mode="HTML")

    for idx, video_id in enumerate(episodes, 1):
        # Aynan siz so'ragan avtomatik format:
        caption_text = f"{title} {idx}-qism Kanal {DEFAULT_CHANNEL_TAG}"
        try:
            await bot.send_video(chat_id=chat_id, video=video_id, caption=caption_text)
            await asyncio.sleep(0.4)
        except Exception as e:
            logging.error(f"Xatolik: {e}")

# ==================== START VA FOYDALANUVCHILAR ====================
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    db_add_user(user_id)

    args = message.text.split()
    code = args[1].strip() if len(args) > 1 else None

    # Majburiy obuna tekshirish
    if not db_is_admin(user_id):
        unsub = await check_user_subscriptions(user_id)
        if unsub:
            await message.answer(
                f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
                "Botdan toʻliq foydalanish uchun quyidagi kanallarga aʼzo boʻling:",
                reply_markup=get_sub_keyboard(unsub, code),
                parse_mode="HTML"
            )
            return

    if code:
        await deliver_anime(user_id, code)
        return

    user_name = message.from_user.first_name
    user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    welcome_text = (
        f"👋 Assalomu alaykum, {user_mention}! Anime botimizga xush kelibsiz.\n"
        f"✍🏻 Anime kodini yuboring..."
    )
    await message.answer(welcome_text, parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("check_sub"))
async def check_sub_cb(call: types.CallbackQuery):
    user_id = call.from_user.id
    unsub = await check_user_subscriptions(user_id)
    code = call.data.replace("check_sub_", "") if "check_sub_" in call.data else None

    if unsub:
        await call.answer("Siz hali barcha kanallarga aʼzo boʻlmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        if code and code != "check_sub":
            await deliver_anime(user_id, code)
        else:
            user_mention = f'<a href="tg://user?id={user_id}">{call.from_user.first_name}</a>'
            await call.message.answer(
                f"👋 Assalomu alaykum, {user_mention}! Anime botimizga xush kelibsiz.\n✍🏻 Anime kodini yuboring...",
                parse_mode="HTML",
                disable_web_page_preview=True
            )

@dp.message(F.text)
async def search_by_code(message: types.Message):
    user_id = message.from_user.id
    db_add_user(user_id)

    if not db_is_admin(user_id):
        unsub = await check_user_subscriptions(user_id)
        if unsub:
            return await message.answer(
                "Botdan foydalanish uchun kanallarga aʼzo boʻling:",
                reply_markup=get_sub_keyboard(unsub, message.text.strip()),
                parse_mode="HTML"
            )

    code = message.text.strip()
    if code.isdigit():
        await deliver_anime(user_id, code)
    else:
        await message.answer("✍🏻 Iltimos, anime kodini (faqat raqam) yuboring:")

# ==================== RENDER 24/7 SERVER ====================
async def health_check(request):
    return web.Response(text="Anime Bot is Running 24/7!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# ==================== ISHGA TUSHIRISH ====================
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    logging.info("Anime boti toʻliq ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
