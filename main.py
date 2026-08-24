import os
import asyncio
import logging
import feedparser
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import google.generativeai as genai

# ==================== SOZLAMALAR ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8530860989:AAFfIgL4OUGUbYctUJAIpz-2j05vun2v9lQ")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Jahon_Chempiyati")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6526733680"))  # Asosiy admin Telegram ID
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 10000))

CHANNEL_TAG = "@Jahon_Chempiyati"
POSTED_NEWS_IDS = set()

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/12040"
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# Gemini AI sozlamasi
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    ai_model = None

# ==================== FSM HOLATLARI ====================
class AdminStates(StatesGroup):
    waiting_topic = State()
    preview_post = State()

# ==================== TUGMALAR ====================
def get_admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Yangi Post Yozish (AI)"), KeyboardButton(text="⚡️ Yangiliklarni Tekshirish")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def get_cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

def get_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Kanalga Joylash", callback_data="publish_post"),
            InlineKeyboardButton(text="🗑 Bekor qilish", callback_data="cancel_preview")
        ]
    ])

# ==================== AI POST TIZIMI ====================
async def generate_football_post(title: str, summary: str) -> str:
    if not ai_model:
        return f"⚽️ <b>{title}</b>\n\n{summary}\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"
    
    prompt = f"""
    Sen professional futbol jurnalisti va sharhlovchisisan.
    Quyidagi futbol yangiligini Telegram kanali uchun juda jozibador, qiziqarli va o'zbek tilida tayyorlab ber.
    
    Yangilik sarlavhasi: {title}
    Qisqacha matn: {summary}
    
    Talablar:
    1. Post boshida jozibali sarlavha va emojilar (🔥, ⚡️, 🚨, ⚽️) qo'y.
    2. Yangilik mohiyatini o'zbek tilida ravon bayon qil.
    3. Post oxirida 1-2 jumlalik qisqacha ekspert tahlili yoki muxlislarga savol qo'sh.
    4. Faqat Telegram HTML teglari (<b>, <i>) ishlatilsin. Markdown (**) ishlatma!
    5. Kanal nomini yozma.
    """
    try:
        response = await asyncio.to_thread(ai_model.generate_content, prompt)
        return f"{response.text.strip()}\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"
    except Exception as e:
        logging.error(f"Gemini AI xatosi: {e}")
        return f"⚽️ <b>{title}</b>\n\n{summary}\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"

async def generate_custom_post(topic: str) -> str:
    prompt = f"""
    Sen professional futbol tahlilchisisan.
    Mavzu: "{topic}"
    Ushbu mavzu bo'yicha Telegram kanali uchun o'ta qiziqarli, tahliliy va to'liq post yozib ber.
    
    Talablar:
    1. Emojilardan unumli foydalan.
    2. Faqat Telegram HTML teglari (<b>, <i>) ishlatilsin. Markdown (**) ishlatma!
    3. Oxirida muxlislar fikrini so'ra.
    4. Kanal nomini yozma.
    """
    try:
        response = await asyncio.to_thread(ai_model.generate_content, prompt)
        return f"{response.text.strip()}\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"
    except Exception as e:
        logging.error(f"Gemini AI xatosi: {e}")
        return f"⚽️ <b>{topic}</b>\n\nPost tayyorlashda xatolik yuz berdi.\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"

# ==================== YANGILIKLARNI AVTOMATIK JOYLASHTIRISH ====================
async def check_and_post_news():
    logging.info("Futbol yangiliklari tekshirilmoqda...")
    for feed_url in RSS_FEEDS:
        try:
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in feed.entries[:3]:
                news_id = entry.get("id", entry.get("link", entry.title))
                if news_id not in POSTED_NEWS_IDS:
                    POSTED_NEWS_IDS.add(news_id)
                    title = entry.title
                    summary = entry.get("summary", "")
                    post = await generate_football_post(title, summary)
                    
                    await bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode="HTML")
                    logging.info(f"Yangi post kanalga tashlandi: {title}")
                    await asyncio.sleep(5)
                    return
        except Exception as e:
            logging.error(f"RSS xatosi: {e}")

# ==================== HANDLERLAR ====================
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Xush kelibsiz, Admin!\n\nQuyidagi admin paneli orqali postlarni boshqarishingiz mumkin:", reply_markup=get_admin_kb())
    else:
        await message.answer(f"👋 Salom {message.from_user.full_name}!\n\nBizning kanal: {CHANNEL_TAG}")

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin Paneli:", reply_markup=get_admin_kb())

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Asosiy menyu:", reply_markup=get_admin_kb() if message.from_user.id == ADMIN_ID else types.ReplyKeyboardRemove())

# --- QO'LDA AI POST TAYYORLASH ---
@dp.message(F.text == "✍️ Yangi Post Yozish (AI)")
async def manual_post_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📝 Post uchun mavzu yoki yangilik matnini yuboring:\n\n<i>Masalan: Mbappe va Vinisius tandemi bu mavsum nechta gol urishi mumkin?</i>", parse_mode="HTML", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.waiting_topic)

@dp.message(AdminStates.waiting_topic)
async def process_topic(message: types.Message, state: FSMContext):
    wait_msg = await message.answer("⏳ AI postni yozmoqda, biroz kuting...")
    post = await generate_custom_post(message.text.strip())
    await wait_msg.delete()
    
    await state.update_data(draft_post=post)
    await message.answer(f"📋 <b>Post ko'rinishi:</b>\n\n{post}", parse_mode="HTML", reply_markup=get_confirm_kb())
    await state.set_state(AdminStates.preview_post)

@dp.callback_query(F.data == "publish_post")
async def publish_post_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post = data.get("draft_post")
    if post:
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode="HTML")
            await call.message.edit_text("✅ Post muvaffaqiyatli kanalga joylandi!")
        except Exception as e:
            await call.message.edit_text(f"❌ Xatolik yuz berdi: {e}")
    await state.clear()

@dp.callback_query(F.data == "cancel_preview")
async def cancel_preview_cb(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("❌ Post bekor qilindi.")
    await state.clear()

# --- YANGILIKLARNI MAJBURAN TEKSHIRISH ---
@dp.message(F.text == "⚡️ Yangiliklarni Tekshirish")
async def force_check(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🔎 Yangiliklar tekshirilmoqda...")
    await check_and_post_news()
    await message.answer("✅ Tekshirish yakunlandi.")

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def stats_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"📊 <b>Bot Statistikasi:</b>\n\n📢 Kanal: {CHANNEL_TAG}\n📤 Bugun e'lon qilingan yangiliklar: {len(POSTED_NEWS_IDS)} ta", parse_mode="HTML")

# ==================== RENDER HEALTH CHECK ====================
async def health_check(request):
    return web.Response(text="Football AI Auto-Post Bot is Running!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# ==================== ASOSIY ISHGA TUSHIRISH ====================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_post_news, "interval", minutes=30)
    scheduler.start()
    
    logging.info("Futbol AI Bot Admin Panel bilan ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
