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
            episodes TEXT,
            upload_type TEXT
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sub_channels (
            channel_id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
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

def db_get_setting(key: str, default=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def db_set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def db_get_sub_channels():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT channel_id, title, url FROM sub_channels")
    rows = cur.fetchall()
    conn.close()
    return rows

# ==================== OBUNA TEKSHIRISH ====================
async def check_user_subscriptions(user_id: int):
    channels = db_get_sub_channels()
    unsubscribed = []
    for ch_id, title, url in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                unsubscribed.append((title, url))
        except Exception:
            continue
    return unsubscribed

def get_sub_keyboard(unsubscribed_channels, ep_callback_data=None):
    keyboard = []
    for title, url in unsubscribed_channels:
        keyboard.append([InlineKeyboardButton(text=f"➕ {title}", url=url)])
    cb_data = f"chk_{ep_callback_data}" if ep_callback_data else "chk_sub"
    keyboard.append([InlineKeyboardButton(text="✅ Aʼzo boʻldim / Tekshirish", callback_data=cb_data)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ==================== TUGMALAR ====================
def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Anime qoʻshish")],
            [KeyboardButton(text="📢 Asosiy kanal"), KeyboardButton(text="🔗 Majburiy kanallar")],
            [KeyboardButton(text="👥 Admin qoʻshish/oʻchirish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="✉️ Xabar yuborish"), KeyboardButton(text="📋 Animelar roʻyxati")],
            [KeyboardButton(text="🗑 Animeni oʻchirish")]
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
    choose_type = State()
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_poster = State()
    waiting_for_desc = State()
    waiting_for_videos = State()
    edit_desc = State()

class MainChannelSetup(StatesGroup):
    waiting_for_channel = State()

class SubChannelManage(StatesGroup):
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

# ==================== 1. ANIME QO'SHISH (2 XIL USUL) ====================
@dp.message(F.text == "🎬 Anime qoʻshish")
async def add_anime_start(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.set_state(AnimeProcess.choose_type)
    
    # 2 xil variant tanlash tugmalari
    type_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎞 1-variant: 1 ta yoki qismlab tashlash", callback_data="type_single")],
        [InlineKeyboardButton(text="📦 2-variant: Toʻliq fasl (Paket) tashlash", callback_data="type_full")]
    ])
    await message.answer(
        "<b>Anime yuklash rejimini tanlang:</b>\n\n"
        "1️⃣ <b>Qismlab tashlash</b> — Faqat bitta yoki alohida qismlar chiqarish uchun.\n"
        "2️⃣ <b>Toʻliq fasl tashlash</b> — Barcha qismlarni toʻliq bitta postda chiqarish uchun.",
        reply_markup=type_kb,
        parse_mode="HTML"
    )

@dp.callback_query(AnimeProcess.choose_type, F.data.in_(["type_single", "type_full"]))
async def process_type_chosen(call: types.CallbackQuery, state: FSMContext):
    upload_type = "single" if call.data == "type_single" else "full"
    await state.update_data(upload_type=upload_type, episodes=[])
    await state.set_state(AnimeProcess.waiting_for_code)
    
    await call.message.delete()
    await call.message.answer(
        "Anime kodini kiriting (masalan: <b>2</b>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(AnimeProcess.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    code = message.text.strip()
    await state.update_data(code=code)
    await state.set_state(AnimeProcess.waiting_for_title)
    await message.answer(
        "Anime nomi va faslini kiriting:\n(Masalan: <b>Omadsizning qayta tugʻilishi [1-fasl]</b>)",
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
    
    await message.answer(
        "Endi anime uchun <b>tavsif (izoh)</b> yuboring:\n<i>(Oʻzingiz xohlagan matnni toʻliq yozishingiz mumkin)</i>",
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
    
    data = await state.get_data()
    utype = data.get("upload_type")
    
    hint = "1 ta qismni tashlang" if utype == "single" else "Barcha qismlarni ketma-ket tashlang"
    await message.answer(
        f"Ajoyib! Endi {hint} (video holida).\n\n"
        "Yuklab boʻlgach, pastdagi <b>«✅ Yakunlandimi?»</b> tugmasini bosing.",
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
        "Yana qismlar boʻlsa tashlayvering, boʻlgach tugmani bosing:",
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
    upload_type = data.get("upload_type", "full")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO animes (code, title, poster, description, episodes, upload_type)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (code, title, poster, desc, json.dumps(episodes), upload_type))
    conn.commit()
    conn.close()

    type_str = "1 qism / Qismlab" if upload_type == "single" else "Toʻliq fasl"
    await call.message.delete()
    await call.message.answer(
        f"✅ <b>Anime muvaffaqiyatli saqlandi!</b>\n\n"
        f"🔢 Kodi: <b>{code}</b>\n"
        f"🏷 Nomi: <b>{title}</b>\n"
        f"📦 Rejim: <b>{type_str}</b>\n"
        f"🎞 Jami qismlar: <b>{len(episodes)} ta</b>\n\n"
        f"📝 <b>Izoh:</b>\n{desc}\n\n"
        f"Quyidagi amallardan birini tanlang:",
        reply_markup=get_anime_management_keyboard(code),
        parse_mode="HTML"
    )
    await state.clear()
    await call.message.answer("Bosh menyudasiz:", reply_markup=get_admin_keyboard())

# --- Kanalga post (faqat izoh), tahrirlash va o'chirish ---
@dp.callback_query(F.data.startswith("send_ch_"))
async def send_to_channel_cb(call: types.CallbackQuery):
    if not db_is_admin(call.from_user.id):
        return
    code = call.data.replace("send_ch_", "")
    main_ch = db_get_setting("main_channel")

    if not main_ch:
        return await call.answer("⚠️ Hali Asosiy kanal kiritilmagan! Avval «📢 Asosiy kanal» boʻlimida kanalni sozlang.", show_alert=True)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT poster, description FROM animes WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return await call.answer("Anime topilmadi!", show_alert=True)

    poster, desc = row
    bot_info = await bot.get_me()

    btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Tomosha qilish 🍿", url=f"https://t.me/{bot_info.username}?start={code}")]
    ])
    try:
        await bot.send_photo(chat_id=main_ch, photo=poster, caption=desc, reply_markup=btn, parse_mode="HTML")
        await call.answer("✅ Kanalga post muvaffaqiyatli yuborildi!", show_alert=True)
    except Exception as e:
        await call.answer(f"❌ Xatolik: {e}\n(Bot {main_ch} kanalida admin ekanligini tekshiring)", show_alert=True)

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

# ==================== 2. ASOSIY KANALNI SOZLASH ====================
@dp.message(F.text == "📢 Asosiy kanal")
async def main_channel_menu(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    current_ch = db_get_setting("main_channel", "Ulanmagan ❌")
    text = (
        f"📢 <b>Asosiy Kanal Sozlamalari (Postlar va Manba uchun):</b>\n\n"
        f"Hozirgi asosiy kanal: <b>{current_ch}</b>\n\n"
        f"Kanalni kiritish yoki oʻzgartirish uchun tugmani bosing:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Asosiy kanalni kiritish / oʻzgartirish", callback_data="set_main_ch_btn")],
        [InlineKeyboardButton(text="🗑 Asosiy kanalni uzish", callback_data="del_main_ch_btn")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "set_main_ch_btn")
async def set_main_ch_prompt(call: types.CallbackQuery, state: FSMContext):
    if not db_is_admin(call.from_user.id):
        return
    await state.set_state(MainChannelSetup.waiting_for_channel)
    await call.message.answer(
        "Asosiy kanal usernamesini yuboring (masalan: <b>@MeningKanalim</b>):\n\n"
        "<i>Eslatma: Post chiqarish uchun bot ushbu kanalda ADMIN boʻlishi kerak!</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(MainChannelSetup.waiting_for_channel)
async def process_set_main_channel(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    ch_text = message.text.strip()
    if not ch_text.startswith("@"):
        ch_text = "@" + ch_text

    db_set_setting("main_channel", ch_text)
    await state.clear()
    await message.answer(f"✅ Asosiy post kanali sifatida <b>{ch_text}</b> saqlandi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "del_main_ch_btn")
async def del_main_ch_cb(call: types.CallbackQuery):
    if not db_is_admin(call.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM settings WHERE key = 'main_channel'")
    conn.commit()
    conn.close()
    await call.answer("Asosiy kanal uzildi!", show_alert=True)
    await call.message.edit_text("Asosiy kanal tozalandi.", reply_markup=None)

# ==================== 3. MAJBURİY KANALLAR ====================
@dp.message(F.text == "🔗 Majburiy kanallar")
async def sub_channels_menu(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    channels = db_get_sub_channels()
    buttons = []
    text = "🔗 <b>Majburiy Obuna Kanallari Roʻyxati:</b>\n<i>(Foydalanuvchi qismni bosganda obuna tekshiriladi)</i>\n\n"
    if channels:
        for ch_id, title, url in channels:
            buttons.append([
                InlineKeyboardButton(text=f"{title}", url=url),
                InlineKeyboardButton(text="❌ Oʻchirish", callback_data=f"del_subch_{ch_id}")
            ])
    else:
        text += "Hozircha majburiy kanal qoʻshilmagan.\n"
    buttons.append([InlineKeyboardButton(text="➕ Majburiy kanal qoʻshish", callback_data="add_subch_btn")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data == "add_subch_btn")
async def add_subch_prompt(call: types.CallbackQuery, state: FSMContext):
    if not db_is_admin(call.from_user.id):
        return
    await state.set_state(SubChannelManage.waiting_for_data)
    await call.message.answer(
        "Majburiy kanalni quyidagi formatda yuboring:\n\n"
        "<code>@KanalUsername|Kanal Nomi|https://t.me/KanalUsername</code>\n\n"
        "<i>Eslatma: Obunani tekshirish uchun bot ushbu kanalda ADMIN boʻlishi kerak!</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(SubChannelManage.waiting_for_data)
async def process_subch_input(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    try:
        parts = message.text.strip().split("|")
        ch_id = parts[0].strip()
        title = parts[1].strip()
        url = parts[2].strip()

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO sub_channels (channel_id, title, url) VALUES (?, ?, ?)", (ch_id, title, url))
        conn.commit()
        conn.close()

        await state.clear()
        await message.answer(f"✅ Majburiy obuna roʻyxatiga <b>{title}</b> qoʻshildi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")
    except Exception:
        await message.answer("❌ Notoʻgʻri format. Quyidagicha yuboring:\n<code>@KanalUsername|Kanal Nomi|https://t.me/KanalUsername</code>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_subch_"))
async def del_subch_cb(call: types.CallbackQuery):
    if not db_is_admin(call.from_user.id):
        return
    ch_id = call.data.replace("del_subch_", "")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM sub_channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()
    await call.answer("Kanal oʻchirildi!", show_alert=True)
    await call.message.delete()

# ==================== 4. ADMIN QO'SHISH/O'CHIRISH ====================
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

# ==================== 5. STATISTIKA ====================
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
    cur.execute("SELECT COUNT(*) FROM sub_channels")
    subch_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM admins")
    admins_cnt = cur.fetchone()[0] + 1
    conn.close()

    main_channel_name = db_get_setting("main_channel", "Ulanmagan")

    await message.answer(
        f"📊 <b>Bot Statistikasi:</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{users_cnt} ta</b>\n"
        f"🎬 Yuklangan animelar: <b>{animes_cnt} ta</b>\n"
        f"📢 Asosiy post kanali: <b>{main_channel_name}</b>\n"
        f"🔗 Majburiy kanallar: <b>{subch_cnt} ta</b>\n"
        f"👥 Adminlar: <b>{admins_cnt} ta</b>",
        parse_mode="HTML"
    )

# ==================== 6. XABAR YUBORISH ====================
@dp.message(F.text == "✉️ Xabar yuborish")
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

# ==================== 7. ANIMELAR RO'YXATI VA O'CHIRISH ====================
@dp.message(F.text == "📋 Animelar roʻyxati")
async def list_animes(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT code, title, episodes, upload_type FROM animes")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return await message.answer("Bazada hali birorta ham anime yoʻq.")

    text = "📋 <b>Mavjud Animelar:</b>\n\n"
    for code, title, eps_json, utype in rows:
        total = len(json.loads(eps_json))
        badge = "📦 Toʻliq" if utype == "full" else "🎞 Qismlab"
        text += f"• Kodi: <code>{code}</code> | <b>{title}</b> ({total} qism) [{badge}]\n"
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

# ==================== FOYDALANUVCHIGA YETKAZIB BERISH ====================
async def deliver_anime(chat_id: int, code: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT title, poster, description, episodes, upload_type FROM animes WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return await bot.send_message(chat_id, "❌ Bunday kodli anime topilmadi. Kodni tekshirib qayta yuboring.")

    title, poster, desc, episodes_json, upload_type = row
    episodes = json.loads(episodes_json)
    total_eps = len(episodes)

    keyboard = []
    
    # Agar 2-variant (Toʻliq fasl) boʻlsa, "Hammasini birdan olish" tugmasi qoʻshiladi
    if upload_type == "full":
        keyboard.append([InlineKeyboardButton(text="📥 Barcha qismlarni toʻliq yuklash", callback_data=f"getall_{code}")])

    # Qismma-qism koʻrish tugmalari (4 tadan)
    row_btns = []
    for idx in range(1, total_eps + 1):
        row_btns.append(InlineKeyboardButton(text=f"{idx}-qism", callback_data=f"getep_{code}_{idx}"))
        if len(row_btns) == 4:
            keyboard.append(row_btns)
            row_btns = []
    if row_btns:
        keyboard.append(row_btns)

    ep_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    caption_text = f"{desc}\n\n👇 <b>Kerakli boʻlimni yoki qismni tanlang:</b>"

    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=poster,
            caption=caption_text,
            reply_markup=ep_markup,
            parse_mode="HTML"
        )
    except Exception:
        await bot.send_message(chat_id=chat_id, text=caption_text, reply_markup=ep_markup, parse_mode="HTML")

# --- 1 ta qism bosilganda ---
@dp.callback_query(F.data.startswith("getep_"))
async def send_single_episode(call: types.CallbackQuery):
    user_id = call.from_user.id
    raw_data = call.data

    # Obunani tekshirish
    if not db_is_admin(user_id):
        unsub = await check_user_subscriptions(user_id)
        if unsub:
            return await call.message.answer(
                f"Assalomu alaykum, <b>{call.from_user.first_name}</b>!\n\n"
                "Qismlarni tomosha qilish uchun quyidagi kanallarga aʼzo boʻling:",
                reply_markup=get_sub_keyboard(unsub, raw_data),
                parse_mode="HTML"
            )

    _, code, ep_num_str = raw_data.split("_")
    ep_num = int(ep_num_str)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT title, episodes FROM animes WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return await call.answer("Anime topilmadi!", show_alert=True)

    title, episodes_json = row
    episodes = json.loads(episodes_json)

    if ep_num <= len(episodes):
        video_id = episodes[ep_num - 1]
        main_channel = db_get_setting("main_channel", "")
        ch_suffix = f" Kanal {main_channel}" if main_channel else ""
        caption_text = f"{title} {ep_num}-qism{ch_suffix}"

        await call.answer(f"{ep_num}-qism yuborilmoqda...")
        await bot.send_video(chat_id=user_id, video=video_id, caption=caption_text)
    else:
        await call.answer("Bu qism topilmadi!", show_alert=True)

# --- Barcha qismlarni toʻliq yuklash bosilganda ---
@dp.callback_query(F.data.startswith("getall_"))
async def send_all_episodes(call: types.CallbackQuery):
    user_id = call.from_user.id
    raw_data = call.data

    # Obuna tekshirish
    if not db_is_admin(user_id):
        unsub = await check_user_subscriptions(user_id)
        if unsub:
            return await call.message.answer(
                f"Assalomu alaykum, <b>{call.from_user.first_name}</b>!\n\n"
                "Barcha qismlarni yuklash uchun quyidagi kanallarga aʼzo boʻling:",
                reply_markup=get_sub_keyboard(unsub, raw_data),
                parse_mode="HTML"
            )

    code = raw_data.replace("getall_", "")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT title, episodes FROM animes WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return await call.answer("Anime topilmadi!", show_alert=True)

    title, episodes_json = row
    episodes = json.loads(episodes_json)
    main_channel = db_get_setting("main_channel", "")
    ch_suffix = f" Kanal {main_channel}" if main_channel else ""

    await call.answer("Barcha qismlar yuklanmoqda...")
    for idx, vid in enumerate(episodes, 1):
        cap = f"{title} {idx}-qism{ch_suffix}"
        try:
            await bot.send_video(chat_id=user_id, video=vid, caption=cap)
            await asyncio.sleep(0.4)
        except Exception as e:
            logging.error(f"Xatolik: {e}")

# --- Obuna boʻlgach tekshirish bosilganda ---
@dp.callback_query(F.data.startswith("chk_"))
async def check_sub_after_action(call: types.CallbackQuery):
    user_id = call.from_user.id
    target_data = call.data.replace("chk_", "")

    unsub = await check_user_subscriptions(user_id)
    if unsub:
        return await call.answer("Siz hali barcha kanallarga aʼzo boʻlmadingiz!", show_alert=True)

    await call.message.delete()

    # Agar 1 ta qism soʻralgan boʻlsa
    if target_data.startswith("getep_"):
        _, code, ep_num_str = target_data.split("_")
        ep_num = int(ep_num_str)

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT title, episodes FROM animes WHERE code = ?", (code,))
        row = cur.fetchone()
        conn.close()

        if row:
            title, episodes_json = row
            episodes = json.loads(episodes_json)
            if ep_num <= len(episodes):
                video_id = episodes[ep_num - 1]
                main_channel = db_get_setting("main_channel", "")
                ch_suffix = f" Kanal {main_channel}" if main_channel else ""
                caption_text = f"{title} {ep_num}-qism{ch_suffix}"
                await bot.send_video(chat_id=user_id, video=video_id, caption=caption_text)

    # Agar toʻliq fasl soʻralgan boʻlsa
    elif target_data.startswith("getall_"):
        code = target_data.replace("getall_", "")
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT title, episodes FROM animes WHERE code = ?", (code,))
        row = cur.fetchone()
        conn.close()

        if row:
            title, episodes_json = row
            episodes = json.loads(episodes_json)
            main_channel = db_get_setting("main_channel", "")
            ch_suffix = f" Kanal {main_channel}" if main_channel else ""
            for idx, vid in enumerate(episodes, 1):
                cap = f"{title} {idx}-qism{ch_suffix}"
                try:
                    await bot.send_video(chat_id=user_id, video=vid, caption=cap)
                    await asyncio.sleep(0.4)
                except Exception:
                    pass

# ==================== START VA QIDIRUV ====================
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    db_add_user(user_id)

    args = message.text.split()
    code = args[1].strip() if len(args) > 1 else None

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

@dp.message(F.text)
async def search_by_code(message: types.Message):
    user_id = message.from_user.id
    db_add_user(user_id)

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
