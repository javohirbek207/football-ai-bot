import os
import asyncio
import logging
import json
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)

# ==================== SOZLAMALAR ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8736913988:AAFCpRN6ytjo6-19gzUfEV3pwYDsPZIxcqo")
MAIN_ADMIN_ID = 8613913673  # Bosh admin (sizning ID raqamingiz)
DEFAULT_CHANNEL = "@Anifible"
PORT = int(os.getenv("PORT", 10000))
DB_NAME = "anime_bot.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== MA'LUMOTLAR BAZASI (SQLITE) ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Animelar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS animes (
                code TEXT PRIMARY KEY,
                title TEXT,
                poster TEXT,
                description TEXT,
                episodes TEXT
            )
        """)
        # Majburiy obuna kanallari jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT
            )
        """)
        # Adminlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Foydalanuvchilar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Bosh adminni avtomatik qo'shish
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (MAIN_ADMIN_ID,))
        # Birlamchi kanalni qo'shish
        await db.execute(
            "INSERT OR IGNORE INTO channels (channel_id, title, url) VALUES (?, ?, ?)",
            (DEFAULT_CHANNEL, "Anifible Rasmiy Kanal", "https://t.me/Anifible")
        )
        await db.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == MAIN_ADMIN_ID:
        return True
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return bool(await cursor.fetchone())

# ==================== MAJBURIY OBUNANI TEKSHIRISH ====================
async def get_required_channels():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT channel_id, title, url FROM channels") as cursor:
            return await cursor.fetchall()

async def check_user_subscriptions(user_id: int):
    channels = await get_required_channels()
    unsubscribed = []
    for ch_id, title, url in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                unsubscribed.append((title, url))
        except Exception as e:
            logging.warning(f"Kanal obunasini tekshirishda xatolik ({ch_id}): {e}")
            continue
    return unsubscribed

def get_sub_keyboard(unsubscribed_channels, code_to_resume=None):
    keyboard = []
    for title, url in unsubscribed_channels:
        keyboard.append([InlineKeyboardButton(text=f"➕ {title}", url=url)])
    cb_data = f"check_sub_{code_to_resume}" if code_to_resume else "check_sub"
    keyboard.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data=cb_data)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ==================== FSM HOLATLAR ====================
class AnimeUpload(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_poster_desc = State()
    uploading_videos = State()
    confirm_channel_post = State()

class ChannelManage(StatesGroup):
    waiting_for_channel = State()

class AdminManage(StatesGroup):
    waiting_for_admin_id = State()

# ==================== ADMIN PANEL MENYUSI ====================
def get_admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Yangi Anime Qo'shish", callback_data="adm_add_anime")],
        [InlineKeyboardButton(text="📢 Majburiy Obuna Kanallari", callback_data="adm_channels"),
         InlineKeyboardButton(text="➕ Kanal Qo'shish", callback_data="adm_add_channel")],
        [InlineKeyboardButton(text="👥 Adminlar Ro'yxati", callback_data="adm_list_admins"),
         InlineKeyboardButton(text="➕ Admin Qo'shish", callback_data="adm_add_admin")],
        [InlineKeyboardButton(text="📊 Bot Statistikasi", callback_data="adm_stats")],
        [InlineKeyboardButton(text="❌ Menyuni yopish", callback_data="adm_close")]
    ])

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        return await message.answer("Siz bot administratori emassiz!")
    await message.answer("🛠 <b>Boshqaruv Paneliga xush kelibsiz:</b>", reply_markup=get_admin_panel_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_close")
async def close_panel(call: types.CallbackQuery):
    await call.message.delete()

# ==================== ADMIN: STATISTIKA ====================
@dp.callback_query(F.data == "adm_stats")
async def show_stats(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            users_count = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM animes") as c2:
            anime_count = (await c2.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM channels") as c3:
            channel_count = (await c3.fetchone())[0]

    text = (
        f"📊 <b>Bot Statistikasi:</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{users_count} ta</b>\n"
        f"🎬 Yuklangan animelar: <b>{anime_count} ta</b>\n"
        f"📢 Faol obuna kanallari: <b>{channel_count} ta</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Ortga", callback_data="adm_back")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "adm_back")
async def back_to_admin(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    await call.message.edit_text("🛠 <b>Boshqaruv Paneliga xush kelibsiz:</b>", reply_markup=get_admin_panel_kb(), parse_mode="HTML")

# ==================== ADMIN: KANALLARNI BOSHQARISH ====================
@dp.callback_query(F.data == "adm_channels")
async def list_channels(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    channels = await get_required_channels()
    if not channels:
        text = "Hozircha majburiy obuna kanallari yo'q."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Ortga", callback_data="adm_back")]])
        return await call.message.edit_text(text, reply_markup=kb)
    
    text = "📢 <b>Majburiy obuna kanallari ro'yxati:</b>\n\nO'chirish uchun kanal yonidagi ❌ tugmasini bosing:\n"
    buttons = []
    for ch_id, title, url in channels:
        buttons.append([
            InlineKeyboardButton(text=f"{title}", url=url),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"del_chan_{ch_id}")
        ])
    buttons.append([InlineKeyboardButton(text="◀️️ Ortga", callback_data="adm_back")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_chan_"))
async def delete_channel(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    ch_id = call.data.replace("del_chan_", "")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
        await db.commit()
    await call.answer("Kanal o'chirildi!", show_alert=True)
    await list_channels(call)

@dp.callback_query(F.data == "adm_add_channel")
async def add_channel_start(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(ChannelManage.waiting_for_channel)
    await call.message.answer(
        "Kanalni qo'shish uchun quyidagi formatda yuboring:\n\n"
        "<code>@KanalUsername|Kanal Nomi|https://t.me/KanalUsername</code>\n\n"
        "<i>Eslatma: Bot ushbu kanalda ADMIN bo'lishi shart!</i>",
        parse_mode="HTML"
    )

@dp.message(ChannelManage.waiting_for_channel)
async def process_add_channel(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    try:
        parts = message.text.strip().split("|")
        ch_id = parts[0].strip()
        title = parts[1].strip()
        url = parts[2].strip()
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT OR REPLACE INTO channels (channel_id, title, url) VALUES (?, ?, ?)", (ch_id, title, url))
            await db.commit()
            
        await message.answer(f"✅ <b>{title}</b> majburiy obuna ro'yxatiga qo'shildi!", parse_mode="HTML")
        await state.clear()
    except Exception:
        await message.answer("❌ Noto'g'ri format. Qaytadan tekshirib yuboring:\n<code>@KanalUsername|Kanal Nomi|https://t.me/KanalUsername</code>", parse_mode="HTML")

# ==================== ADMIN: YORDAMCHI ADMINLARNI BOSHQARISH ====================
@dp.callback_query(F.data == "adm_list_admins")
async def list_admins(call: types.CallbackQuery):
    if call.from_user.id != MAIN_ADMIN_ID:
        return await call.answer("Faqat bosh admin adminlarni ko'ra oladi!", show_alert=True)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM admins") as c:
            admins = await c.fetchall()

    text = "👥 <b>Adminlar ro'yxati:</b>\n\n"
    buttons = []
    for (adm_id,) in admins:
        badge = "👑 Bosh Admin" if adm_id == MAIN_ADMIN_ID else "Admin"
        row = [InlineKeyboardButton(text=f"ID: {adm_id} ({badge})", callback_data="none")]
        if adm_id != MAIN_ADMIN_ID:
            row.append(InlineKeyboardButton(text="❌ O'chirish", callback_data=f"del_adm_{adm_id}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Ortga", callback_data="adm_back")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_adm_"))
async def delete_admin(call: types.CallbackQuery):
    if call.from_user.id != MAIN_ADMIN_ID:
        return
    target_id = int(call.data.replace("del_adm_", ""))
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        await db.commit()
    await call.answer("Admin muvaffaqiyatli olib tashlandi!", show_alert=True)
    await list_admins(call)

@dp.callback_query(F.data == "adm_add_admin")
async def add_admin_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != MAIN_ADMIN_ID:
        return await call.answer("Faqat bosh admin yangi admin qo'sha oladi!", show_alert=True)
    await state.set_state(AdminManage.waiting_for_admin_id)
    await call.message.answer("Yangi adminning Telegram <b>raqamli ID</b> sini yuboring:", parse_mode="HTML")

@dp.message(AdminManage.waiting_for_admin_id)
async def process_add_admin(message: types.Message, state: FSMContext):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    text = message.text.strip()
    if not text.isdigit():
        return await message.answer("Iltimos, faqat raqamlardan iborat ID kiriting.")
    new_admin_id = int(text)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        await db.commit()
    await message.answer(f"✅ Foydalanuvchi (ID: <code>{new_admin_id}</code>) admin etib tayinlandi!", parse_mode="HTML")
    await state.clear()

# ==================== ADMIN: ANIME YUKLASH TIZIMI ====================
@dp.callback_query(F.data == "adm_add_anime")
async def add_anime_start(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AnimeUpload.waiting_for_code)
    await call.message.answer("Anime kodini kiriting (masalan: <b>101</b>):", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")

@dp.message(AnimeUpload.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    code = message.text.strip()
    await state.update_data(code=code, episodes=[])
    await state.set_state(AnimeUpload.waiting_for_title)
    await message.answer("Anime nomi va faslini kiriting:\nMasalan: <b>Omadsizning qayta tug'ilishi [1-fasl]</b>", parse_mode="HTML")

@dp.message(AnimeUpload.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AnimeUpload.waiting_for_poster_desc)
    await message.answer("Anime posterini (rasm) tashlang va uning izohiga (caption) tavsif yozing:")

@dp.message(AnimeUpload.waiting_for_poster_desc, F.photo)
async def process_poster_desc(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    photo_id = message.photo[-1].file_id
    desc = message.caption or "Anime haqida qisqacha ma'lumot."
    await state.update_data(poster=photo_id, desc=desc)
    
    await state.set_state(AnimeUpload.uploading_videos)
    finish_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Yuklashni yakunlash")]],
        resize_keyboard=True
    )
    await message.answer(
        "Ajoyib! Endi animening barcha qismlarini (video ko'rinishida) navbatma-navbat tashlang.\n\n"
        "Barcha qismlarni tashlab bo'lgach, pastdagi <b>«✅ Yuklashni yakunlash»</b> tugmasini bosing.",
        reply_markup=finish_kb,
        parse_mode="HTML"
    )

@dp.message(AnimeUpload.uploading_videos, F.video)
async def process_video(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    episodes.append(message.video.file_id)
    await state.update_data(episodes=episodes)
    await message.answer(f"✅ <b>{len(episodes)}-qism</b> qabul qilindi.", parse_mode="HTML")

@dp.message(AnimeUpload.uploading_videos, F.text == "✅ Yuklashni yakunlash")
async def finish_videos(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    if not episodes:
        return await message.answer("Kamida 1 ta video yuborishingiz kerak!")

    code = data["code"]
    title = data["title"]
    poster = data["poster"]
    desc = data["desc"]

    # SQLite bazasiga saqlaymiz
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO animes (code, title, poster, description, episodes)
            VALUES (?, ?, ?, ?, ?)
        """, (code, title, poster, desc, json.dumps(episodes)))
        await db.commit()

    await state.set_state(AnimeUpload.confirm_channel_post)
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Ha, yuborilsin 🚀", callback_data="post_yes"),
            InlineKeyboardButton(text="Yo'q, shart emas ❌", callback_data="post_no")
        ]
    ])

    await message.answer(
        f"✅ <b>Anime saqlandi!</b>\n\n"
        f"🔢 Kodi: <b>{code}</b>\n"
        f"🏷 Nomi: <b>{title}</b>\n"
        f"🎞 Qismlar: <b>{len(episodes)} ta</b>\n\n"
        f"<b>Kanalga e'lon posti yuborilsinmi?</b>",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )

@dp.callback_query(AnimeUpload.confirm_channel_post, F.data.in_(["post_yes", "post_no"]))
async def handle_post_decision(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    desc = data["desc"]
    poster = data["poster"]
    total_episodes = len(data["episodes"])
    
    bot_info = await bot.get_me()

    if call.data == "post_yes":
        channel_post_text = (
            f"🎬 <b>Yangi Anime Joylandi!</b>\n\n"
            f"🏷 <b>Nomi:</b> {title}\n"
            f"🔢 <b>Kodi:</b> <code>{code}</code>\n"
            f"🎞 <b>Qismlar soni:</b> {total_episodes} ta\n\n"
            f"📝 <b>Tavsif:</b>\n{desc}\n\n"
            f"Tomosha qilish uchun pastdagi tugmani bosing yoki botga <code>{code}</code> kodini yuboring.\n\n"
            f"Kanal: {DEFAULT_CHANNEL}"
        )
        btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Tomosha qilish 🍿", url=f"https://t.me/{bot_info.username}?start={code}")]
        ])
        try:
            await bot.send_photo(chat_id=DEFAULT_CHANNEL, photo=poster, caption=channel_post_text, reply_markup=btn, parse_mode="HTML")
            await call.message.edit_text("✅ Kanalga post muvaffaqiyatli yuborildi!", reply_markup=None)
        except Exception as e:
            await call.message.edit_text(f"❌ Kanalga yuborishda xatolik: {e}", reply_markup=None)
    else:
        await call.message.edit_text("Post kanalga yuborilmadi. Anime faqat bot bazasida qoldi.", reply_markup=None)

    await state.clear()

# ==================== ANIME QISMLARINI YUBORISH ====================
async def deliver_anime(chat_id: int, code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT title, episodes FROM animes WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()

    if not row:
        return await bot.send_message(chat_id, "❌ Bunday kodli anime topilmadi. Kodni tekshirib qaytadan yuboring.")

    title, episodes_json = row
    episodes = json.loads(episodes_json)

    await bot.send_message(chat_id, f"🎬 <b>{title}</b> qismlari yuklanmoqda...", parse_mode="HTML")

    for idx, video_id in enumerate(episodes, 1):
        # Talabingiz bo'yicha aniq format:
        caption = f"{title} {idx}-qism\nKanal: {DEFAULT_CHANNEL}"
        try:
            await bot.send_video(chat_id=chat_id, video=video_id, caption=caption)
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f"Video yuborishda xato: {e}")

# ==================== FOYDALANUVCHILAR UCHUN START VA QIDIRUV ====================
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    # Foydalanuvchini bazaga qo'shish
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()

    args = message.text.split()
    code = args[1].strip() if len(args) > 1 else None

    # Majburiy obunani tekshirish
    unsub = await check_user_subscriptions(user_id)
    if unsub:
        await message.answer(
            f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
            f"Botdan to'liq foydalanish va animelarni tomosha qilish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=get_sub_keyboard(unsub, code),
            parse_mode="HTML"
        )
        return

    if code:
        await deliver_anime(user_id, code)
    else:
        await message.answer(
            f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
            f"Bu <b>{DEFAULT_CHANNEL}</b> rasmiy anime boti.\n"
            "Tomosha qilmoqchi bo'lgan animenang kodini yuboring (masalan: <code>101</code>):",
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("check_sub"))
async def check_sub_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    unsub = await check_user_subscriptions(user_id)
    code = call.data.replace("check_sub_", "") if "check_sub_" in call.data else None

    if unsub:
        await call.answer("Siz hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi! Xush kelibsiz.")
        if code and code != "check_sub":
            await deliver_anime(user_id, code)
        else:
            await call.message.answer("Marhamat, ko'rmoqchi bo'lgan anime kodini yuboring:")

@dp.message(F.text)
async def code_search_handler(message: types.Message):
    user_id = message.from_user.id
    # Majburiy obuna tekshiruvi
    unsub = await check_user_subscriptions(user_id)
    if unsub:
        return await message.answer(
            "Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:",
            reply_markup=get_sub_keyboard(unsub, message.text.strip()),
            parse_mode="HTML"
        )

    code = message.text.strip()
    if code.isdigit():
        await deliver_anime(user_id, code)
    else:
        await message.answer("Iltimos, faqat anime kodini (masalan: <code>101</code>) yuboring.", parse_mode="HTML")

# ==================== RENDER HEALTH CHECK ====================
async def health_check(request):
    return web.Response(text="Anime Bot with Full Admin Panel is Running 24/7!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# ==================== ASOSIY ISHGA TUSHIRISH ====================
async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    logging.info("Mukammal Anime Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
