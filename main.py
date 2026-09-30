import os
import asyncio
import logging
import json
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

# ==================== ASOSIY SOZLAMALAR ====================
BOT_TOKEN = "8736913988:AAEt_b45vOcUE-VwVFY_R1hM0Vv0TvXhtCg"
MAIN_ADMIN_ID = 8613913673
PORT = int(os.getenv("PORT", 10000))
DB_NAME = "anime_data.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== MA'LUMOTLAR BAZASI (SQLITE) ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Animelar
    cur.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            code TEXT PRIMARY KEY,
            title TEXT,
            poster TEXT,
            description TEXT,
            episodes TEXT
        )
    """)
    # Foydalanuvchilar
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    # Yordamchi adminlar
    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    # Sozlamalar (kanal va boshqalar)
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

# ==================== TUGMALAR MENYUSI ====================
def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Yangi Anime Yuklash")],
            [KeyboardButton(text="📢 Kanalni Sozlash"), KeyboardButton(text="👥 Adminlar Boshqaruvi")],
            [KeyboardButton(text="✉️ Xabar Yuborish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📋 Animelar Ro'yxati"), KeyboardButton(text="🗑 Animeni O'chirish")]
        ],
        resize_keyboard=True
    )

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def get_finish_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Yuklashni yakunlash")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

# ==================== FSM BOSQICHLARI ====================
class AnimeUpload(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_poster_desc = State()
    uploading_videos = State()
    confirm_channel_post = State()

class AnimeDelete(StatesGroup):
    waiting_for_code = State()

class ChannelSetup(StatesGroup):
    waiting_for_channel = State()

class AdminAdd(StatesGroup):
    waiting_for_id = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

# ==================== BEKOR QILISH ====================
@dp.message(F.text == "❌ Bekor qilish")
async def cancel_action(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Jarayon bekor qilindi. Bosh menyudasiz:", reply_markup=get_admin_keyboard())

# ==================== 1. ANIME YUKLASH ====================
@dp.message(F.text == "🎬 Yangi Anime Yuklash")
async def add_anime_start(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.set_state(AnimeUpload.waiting_for_code)
    await message.answer("Anime kodini kiriting (masalan: <b>101</b>):", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AnimeUpload.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    code = message.text.strip()
    await state.update_data(code=code, episodes=[])
    await state.set_state(AnimeUpload.waiting_for_title)
    await message.answer("Anime nomini kiriting:\n(Masalan: <b>Omadsizning qayta tug'ilishi [1-fasl]</b>)", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AnimeUpload.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(AnimeUpload.waiting_for_poster_desc)
    await message.answer("Anime posterini (rasm) tashlang va izohiga tavsif yozing:", reply_markup=get_cancel_keyboard())

@dp.message(AnimeUpload.waiting_for_poster_desc, F.photo)
async def process_poster_desc(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    photo_id = message.photo[-1].file_id
    desc = message.caption or "Anime tavsifi mavjud emas."
    await state.update_data(poster=photo_id, desc=desc)
    await state.set_state(AnimeUpload.uploading_videos)
    await message.answer(
        "Endi animening barcha qismlarini (video holida) ketma-ket tashlang.\n\n"
        "Barcha qismlarni tashlab bo'lgach, pastdagi <b>«✅ Yuklashni yakunlash»</b> tugmasini bosing.",
        reply_markup=get_finish_keyboard(),
        parse_mode="HTML"
    )

@dp.message(AnimeUpload.uploading_videos, F.video)
async def process_video(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    episodes.append(message.video.file_id)
    await state.update_data(episodes=episodes)
    await message.answer(f"✅ <b>{len(episodes)}-qism</b> qabul qilindi.", parse_mode="HTML")

@dp.message(AnimeUpload.uploading_videos, F.text == "✅ Yuklashni yakunlash")
async def finish_videos(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    if not episodes:
        return await message.answer("Kamida 1 ta video yuklashingiz kerak!")

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

    await state.set_state(AnimeUpload.confirm_channel_post)
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Ha, yuborilsin 🚀", callback_data="post_yes"),
            InlineKeyboardButton(text="Yo'q, shart emas ❌", callback_data="post_no")
        ]
    ])
    await message.answer(
        f"✅ <b>Anime saqlandi!</b>\n\n"
        f"Kodi: <b>{code}</b>\n"
        f"Nomi: <b>{title}</b>\n"
        f"Qismlar soni: <b>{len(episodes)} ta</b>\n\n"
        f"<b>Kanalga e'lon posti yuborilsinmi?</b>",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )

@dp.callback_query(AnimeUpload.confirm_channel_post, F.data.in_(["post_yes", "post_no"]))
async def handle_post_decision(call: types.CallbackQuery, state: FSMContext):
    if not db_is_admin(call.from_user.id):
        return
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    desc = data["desc"]
    poster = data["poster"]
    total = len(data["episodes"])
    bot_info = await bot.get_me()

    channel_target = db_get_setting("post_channel")

    if call.data == "post_yes":
        if not channel_target:
            await call.message.edit_text(
                "⚠️ Post yuboriladigan kanal hali ulanmagan!\n"
                "Admin paneldagi <b>«📢 Kanalni Sozlash»</b> tugmasi orqali kanal usernamesini kiriting.\n"
                "Anime esa bot bazasida saqlanib qoldi.",
                parse_mode="HTML"
            )
        else:
            channel_post_text = (
                f"🎬 <b>Yangi Anime Joylandi!</b>\n\n"
                f"🏷 <b>Nomi:</b> {title}\n"
                f"🔢 <b>Kodi:</b> <code>{code}</code>\n"
                f"🎞 <b>Qismlar:</b> {total} ta\n\n"
                f"📝 <b>Tavsif:</b>\n{desc}\n\n"
                f"Kanal: {channel_target}"
            )
            btn = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Tomosha qilish 🍿", url=f"https://t.me/{bot_info.username}?start={code}")]
            ])
            try:
                await bot.send_photo(chat_id=channel_target, photo=poster, caption=channel_post_text, reply_markup=btn, parse_mode="HTML")
                await call.message.edit_text("✅ Kanalga post muvaffaqiyatli yuborildi!", reply_markup=None)
            except Exception as e:
                await call.message.edit_text(
                    f"❌ Kanalga yuborib bo'lmadi.\nSabab: {e}\n"
                    f"<i>(Bot <b>{channel_target}</b> kanalida admin ekanligiga va 'Post messages' ruxsati borligiga ishonch hosil qiling)</i>",
                    parse_mode="HTML",
                    reply_markup=None
                )
    else:
        await call.message.edit_text("Post kanalga yuborilmadi. Anime botda saqlandi.", reply_markup=None)

    await state.clear()
    await call.message.answer("Bosh menyudasiz:", reply_markup=get_admin_keyboard())

# ==================== 2. KANALNI QO'LDA SOZLASH ====================
@dp.message(F.text == "📢 Kanalni Sozlash")
async def channel_setup_menu(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    current_ch = db_get_setting("post_channel", "Ulanmagan ❌")
    
    text = (
        f"📢 <b>Kanal Sozlamalari:</b>\n\n"
        f"Hozirgi e'lon kanali: <b>{current_ch}</b>\n\n"
        f"Kanalni kiritish yoki o'zgartirish uchun quyidagi tugmani bosing:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Kanalni o'zgartirish / kiritish", callback_data="set_channel_btn")],
        [InlineKeyboardButton(text="🗑 Kanalni uzish", callback_data="unlink_channel_btn")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "set_channel_btn")
async def set_channel_prompt(call: types.CallbackQuery, state: FSMContext):
    if not db_is_admin(call.from_user.id):
        return
    await state.set_state(ChannelSetup.waiting_for_channel)
    await call.message.answer(
        "Kanal usernamesini yuboring (masalan: <b>@Anifible</b>):\n\n"
        "<i>Eslatma: Kanalga post chiqarishdan oldin botni o'sha kanalda admin qiling!</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(ChannelSetup.waiting_for_channel)
async def process_set_channel(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    ch_text = message.text.strip()
    if not ch_text.startswith("@"):
        ch_text = "@" + ch_text
    
    db_set_setting("post_channel", ch_text)
    await state.clear()
    await message.answer(f"✅ E'lon kanali sifatida <b>{ch_text}</b> muvaffaqiyatli saqlandi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "unlink_channel_btn")
async def unlink_channel_cb(call: types.CallbackQuery):
    if not db_is_admin(call.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM settings WHERE key = 'post_channel'")
    conn.commit()
    conn.close()
    await call.answer("Kanal uzildi!", show_alert=True)
    await call.message.edit_text("Kanal sozlamasi olib tashlandi. Hozirda hech qanday kanal ulanmagan.", reply_markup=None)

# ==================== 3. ADMINLAR BOSHQARUVI ====================
@dp.message(F.text == "👥 Adminlar Boshqaruvi")
async def admins_manage_menu(message: types.Message):
    if message.from_user.id != MAIN_ADMIN_ID:
        return await message.answer("Faqat Bosh Admin boshqa adminlarni boshqara oladi.")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    admins = cur.fetchall()
    conn.close()

    text = f"👥 <b>Bot Adminlari:</b>\n\n👑 <b>Bosh Admin:</b> <code>{MAIN_ADMIN_ID}</code>\n"
    buttons = []
    for (adm_id,) in admins:
        buttons.append([
            InlineKeyboardButton(text=f"ID: {adm_id}", callback_data="none"),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"del_admin_{adm_id}")
        ])
    buttons.append([InlineKeyboardButton(text="➕ Yangi Admin Qo'shish", callback_data="add_new_admin")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data == "add_new_admin")
async def add_admin_prompt(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != MAIN_ADMIN_ID:
        return await call.answer("Faqat bosh admin bajara oladi!", show_alert=True)
    await state.set_state(AdminAdd.waiting_for_id)
    await call.message.answer("Yangi adminning Telegram <b>raqamli ID</b> sini yuboring:", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AdminAdd.waiting_for_id)
async def process_admin_add(message: types.Message, state: FSMContext):
    if message.from_user.id != MAIN_ADMIN_ID:
        return
    text = message.text.strip()
    if not text.isdigit():
        return await message.answer("Faqat raqamlardan iborat ID kiriting.")
    new_id = int(text)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer(f"✅ ID <code>{new_id}</code> bo'lgan foydalanuvchi admin qilindi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_admin_"))
async def process_admin_del(call: types.CallbackQuery):
    if call.from_user.id != MAIN_ADMIN_ID:
        return
    adm_id = int(call.data.replace("del_admin_", ""))
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE user_id = ?", (adm_id,))
    conn.commit()
    conn.close()
    await call.answer("Admin muvaffaqiyatli o'chirildi!", show_alert=True)
    await call.message.delete()

# ==================== 4. STATISTIKA ====================
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM animes")
    animes_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM admins")
    admins_cnt = cur.fetchone()[0] + 1
    conn.close()

    channel_curr = db_get_setting("post_channel", "Ulanmagan")

    text = (
        f"📊 <b>Bot Statistikasi:</b>\n\n"
        f"👤 Jami a'zolar: <b>{users_cnt} ta</b>\n"
        f"🎬 Yuklangan animelar: <b>{animes_cnt} ta</b>\n"
        f"📢 Ulangan e'lon kanali: <b>{channel_curr}</b>\n"
        f"👥 Adminlar soni: <b>{admins_cnt} ta</b>"
    )
    await message.answer(text, parse_mode="HTML")

# ==================== 5. XABAR YUBORISH (BROADCAST) ====================
@dp.message(F.text == "✉️ Xabar Yuborish")
async def broadcast_prompt(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer(
        "Barcha bot foydalanuvchilariga yuboriladigan xabarni (matn, rasm yoki video) yuboring:",
        reply_markup=get_cancel_keyboard()
    )

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
        f"Yetib bormadi (bloklaganlar): <b>{failed} ta</b>",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )

# ==================== 6. ANIMELAR RO'YXATI VA O'CHIRISH ====================
@dp.message(F.text == "📋 Animelar Ro'yxati")
async def list_animes(message: types.Message):
    if not db_is_admin(message.from_user.id):
        return
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT code, title, episodes FROM animes")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return await message.answer("Bazada hali birorta ham anime mavjud emas.")
    
    text = "📋 <b>Mavjud Animelar Ro'yxati:</b>\n\n"
    for code, title, eps_json in rows:
        total = len(json.loads(eps_json))
        text += f"• Kodi: <code>{code}</code> | <b>{title}</b> ({total} qism)\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🗑 Animeni O'chirish")
async def delete_anime_prompt(message: types.Message, state: FSMContext):
    if not db_is_admin(message.from_user.id):
        return
    await state.set_state(AnimeDelete.waiting_for_code)
    await message.answer("O'chirmoqchi bo'lgan anime kodini yuboring:", reply_markup=get_cancel_keyboard())

@dp.message(AnimeDelete.waiting_for_code)
async def process_delete_anime(message: types.Message, state: FSMContext):
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
        await message.answer(f"✅ Kod <code>{code}</code> bo'lgan anime o'chirildi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")
    else:
        await message.answer("❌ Bunday kodli anime topilmadi.", reply_markup=get_admin_keyboard())

# ==================== ANIME QISMLARINI YUBORISH (TOZA HOLDA) ====================
async def deliver_anime(chat_id: int, code: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT title, episodes FROM animes WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return await bot.send_message(chat_id, "❌ Bunday kodli kino/anime topilmadi. Kodni tekshirib qayta yuboring.")

    title, episodes_json = row
    episodes = json.loads(episodes_json)

    await bot.send_message(chat_id, f"🎬 <b>{title}</b> qismlari yuklanmoqda...", parse_mode="HTML")

    for video_id in episodes:
        try:
            # Butunlay toza video (hech qanday caption/matnsiz)
            await bot.send_video(chat_id=chat_id, video=video_id)
            await asyncio.sleep(0.4)
        except Exception as e:
            logging.error(f"Video yuborishda xato: {e}")

# ==================== FOYDALANUVCHILAR VA START ====================
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    db_add_user(user_id)
    bot_info = await bot.get_me()

    args = message.text.split()
    code = args[1].strip() if len(args) > 1 else None

    # Deep-link orqali kod bilan kirganda to'g'ridan-to'g'ri qismlarni yuborish
    if code:
        await deliver_anime(user_id, code)
        return

    # Admin kirganda
    if db_is_admin(user_id):
        admin_text = (
            f"👋 Assalomu alaykum, <a href=\"tg://user?id={user_id}\">{message.from_user.first_name}</a>!\n\n"
            f"🛠 <b>Siz uchun Boshqaruv Menyusi faol:</b>"
        )
        await message.answer(
            admin_text,
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    # Oddiy foydalanuvchi kirganda
    else:
        welcome_text = (
            f"👋 Assalomu alaykum <a href=\"https://t.me/{bot_info.username}\">𝑻𝒚𝒄𝒍𝒐𝒎</a> botimizga xush kelibsiz. "
            f"✍🏻 Kino kodini yuboring..."
        )
        await message.answer(
            welcome_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

@dp.message(F.text)
async def search_by_code(message: types.Message):
    user_id = message.from_user.id
    db_add_user(user_id)

    code = message.text.strip()
    if code.isdigit():
        await deliver_anime(user_id, code)
    else:
        await message.answer("✍🏻 Iltimos, kino kodini (faqat raqam) yuboring:")

# ==================== RENDER SERVER (24/7 UPTIME) ====================
async def health_check(request):
    return web.Response(text="Tyclom Anime Bot is Running 24/7!", status=200)

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
    logging.info("Tyclom Anime/Kino boti to'liq ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
