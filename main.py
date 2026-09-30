import os
import asyncio
import logging
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

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8736913988:AAFCpRN6ytjo6-19gzUfEV3pwYDsPZIxcqo"
ADMIN_ID = 8613913673
CHANNEL_TAG = "@Anifible"
PORT = int(os.getenv("PORT", 10000))

# Animelar bazasi
anime_db = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== TUGMALAR MENYUSI ====================
def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Yangi Anime Yuklash")],
            [KeyboardButton(text="📊 Animelar Ro'yxati"), KeyboardButton(text="🗑 Animeni O'chirish")]
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

# ==================== BEKOR QILISH TUGMASI ====================
@dp.message(F.text == "❌ Bekor qilish")
async def cancel_action(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("Jarayon bekor qilindi. Bosh menyudasiz:", reply_markup=get_admin_keyboard())

# ==================== ANIME YUKLASH TUGMASI ====================
@dp.message(F.text == "🎬 Yangi Anime Yuklash")
async def add_anime_btn_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AnimeUpload.waiting_for_code)
    await message.answer("Anime kodini yozing (masalan: <b>101</b>):", reply_markup=get_cancel_keyboard(), parse_mode="HTML")

@dp.message(AnimeUpload.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip()
    await state.update_data(code=code, episodes=[])
    await state.set_state(AnimeUpload.waiting_for_title)
    await message.answer(
        "Anime nomini kiriting:\n(Masalan: <b>Omadsizning qayta tug'ilishi [1-fasl]</b>)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(AnimeUpload.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AnimeUpload.waiting_for_poster_desc)
    await message.answer(
        "Anime posterini (rasm) tashlang va uning izohiga tavsif yozing:",
        reply_markup=get_cancel_keyboard()
    )

@dp.message(AnimeUpload.waiting_for_poster_desc, F.photo)
async def process_poster_desc(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    photo_id = message.photo[-1].file_id
    desc = message.caption or "Anime tavsifi."
    await state.update_data(poster=photo_id, desc=desc)
    
    await state.set_state(AnimeUpload.uploading_videos)
    await message.answer(
        "Endi animening barcha qismlarini (video holida) ketma-ket tashlang.\n\n"
        "Barcha qismlarni yuklab bo'lgach, pastdagi <b>«✅ Yuklashni yakunlash»</b> tugmasini bosing.",
        reply_markup=get_finish_keyboard(),
        parse_mode="HTML"
    )

@dp.message(AnimeUpload.uploading_videos, F.video)
async def process_video(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    episodes.append(message.video.file_id)
    await state.update_data(episodes=episodes)
    await message.answer(f"✅ <b>{len(episodes)}-qism</b> qabul qilindi.", parse_mode="HTML")

@dp.message(AnimeUpload.uploading_videos, F.text == "✅ Yuklashni yakunlash")
async def finish_videos(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    
    if not episodes:
        return await message.answer("Kamida bitta qism (video) yuklashingiz kerak!")

    code = data["code"]
    title = data["title"]
    anime_db[code] = {
        "title": title,
        "poster": data["poster"],
        "desc": data["desc"],
        "episodes": episodes
    }
    
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
    if call.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    desc = data["desc"]
    poster = data["poster"]
    total = len(data["episodes"])
    
    bot_info = await bot.get_me()

    if call.data == "post_yes":
        channel_post_text = (
            f"🎬 <b>Yangi Anime Joylandi!</b>\n\n"
            f"🏷 <b>Nomi:</b> {title}\n"
            f"🔢 <b>Kodi:</b> <code>{code}</code>\n"
            f"🎞 <b>Qismlar:</b> {total} ta\n\n"
            f"📝 <b>Tavsif:</b>\n{desc}\n\n"
            f"Kanal: {CHANNEL_TAG}"
        )
        btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Tomosha qilish 🍿", url=f"https://t.me/{bot_info.username}?start={code}")]
        ])
        try:
            await bot.send_photo(chat_id=CHANNEL_TAG, photo=poster, caption=channel_post_text, reply_markup=btn, parse_mode="HTML")
            await call.message.edit_text("✅ Kanalga post muvaffaqiyatli yuborildi!", reply_markup=None)
        except Exception as e:
            await call.message.edit_text(f"❌ Kanalga yuborishda xatolik: {e}\n(Bot kanalda admin ekanligini tekshiring)", reply_markup=None)
    else:
        await call.message.edit_text("Post kanalga yuborilmadi. Anime faqat botda saqlandi.", reply_markup=None)

    await state.clear()
    await call.message.answer("Bosh menyudasiz:", reply_markup=get_admin_keyboard())

# ==================== BOSHQA ADMIN TUGMALARI ====================
@dp.message(F.text == "📊 Animelar Ro'yxati")
async def list_animes_btn(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not anime_db:
        return await message.answer("Bazada hali birorta ham anime yo'q.")
    
    text = "📊 <b>Bazada mavjud animelar:</b>\n\n"
    for code, data in anime_db.items():
        text += f"• Kodi: <code>{code}</code> | <b>{data['title']}</b> ({len(data['episodes'])} qism)\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🗑 Animeni O'chirish")
async def delete_anime_btn(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AnimeDelete.waiting_for_code)
    await message.answer("O'chirmoqchi bo'lgan anime kodini yuboring:", reply_markup=get_cancel_keyboard())

@dp.message(AnimeDelete.waiting_for_code)
async def process_delete(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip()
    if code in anime_db:
        del anime_db[code]
        await message.answer(f"✅ Kod <code>{code}</code> bo'lgan anime o'chirildi!", reply_markup=get_admin_keyboard(), parse_mode="HTML")
    else:
        await message.answer("❌ Bunday kodli anime topilmadi.", reply_markup=get_admin_keyboard())
    await state.clear()

# ==================== QISMLARNI CHIQARISH (TOZA HOLDA) ====================
async def deliver_anime(chat_id: int, code: str):
    if code not in anime_db:
        return await bot.send_message(chat_id, "❌ Bunday kodli anime topilmadi. Kodni to'g'ri kiritganingizni tekshiring.")

    anime = anime_db[code]
    title = anime["title"]
    episodes = anime["episodes"]

    await bot.send_message(chat_id, f"🎬 <b>{title}</b> barcha qismlari yuklanmoqda...", parse_mode="HTML")

    for video_id in episodes:
        try:
            # Hech qanday yozuvsiz (caption yo'q) sof video yuboriladi
            await bot.send_video(chat_id=chat_id, video=video_id)
            await asyncio.sleep(0.4)
        except Exception as e:
            logging.error(f"Xatolik: {e}")

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    args = message.text.split()
    if len(args) > 1:
        code = args[1].strip()
        await deliver_anime(message.chat.id, code)
        return

    if message.from_user.id == ADMIN_ID:
        await message.answer(
            f"Salom Bosh Admin, <b>{message.from_user.first_name}</b>!\n\n"
            "Admin paneldasiz. Quyidagi tugmalar orqali anime yuklashingiz yoki boshqarishingiz mumkin:",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
            f"Bu <b>{CHANNEL_TAG}</b> rasmiy anime boti.\n"
            "Tomosha qilmoqchi bo'lgan anime kodini yozing (masalan: <code>101</code>):",
            parse_mode="HTML"
        )

@dp.message(F.text)
async def search_by_code(message: types.Message):
    code = message.text.strip()
    if code.isdigit():
        await deliver_anime(message.chat.id, code)
    else:
        await message.answer("Iltimos, faqat anime kodini (raqam) yuboring.")

# ==================== RENDER WEB SERVER ====================
async def health_check(request):
    return web.Response(text="Anime Bot is Live!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# ==================== ASOSIY FUNKSIYA ====================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    logging.info("Anime bot toza holatda ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
