import os
import asyncio
import logging
import feedparser
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai

# ==================== SOZLAMALAR ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8530860989:AAFfIgL4OUGUbYctUJAIpz-2j05vun2v9lQ")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@kanalingiz_usernamesi") # Masalan: @realmadrid_uz yoki -100123456789
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 10000))

# Xabarlar takrorlanmasligi uchun xotira
POSTED_NEWS_IDS = set()

# Futbol RSS Manbalari (BBC Sport va SkySports)
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/12040"
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# Gemini AI Client
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ==================== AI ORQALI POST TAYYORLASH ====================
async def generate_football_post(title: str, summary: str) -> str:
    if not ai_client:
        return f"⚽️ <b>{title}</b>\n\n{summary}\n\n📢 @{CHANNEL_ID.replace('@', '')}"
    
    prompt = f"""
    Sen professional futbol jurnalisti va tahlilchisisan.
    Quyidagi futbol yangiligini Telegram kanali uchun juda chiroyli, qiziqarli va o'zbek tilida tayyorlab ber.
    
    Yangilik sarlavhasi: {title}
    Qisqacha matn: {summary}
    
    Talablar:
    1. Post boshida chiroyli sarlavha va emojilar (🔥, ⚡️, 🚨, ⚽️) bo'lsin.
    2. Yangilik mohiyatini o'zbek tilida ravon bayon qil.
    3. Post oxirida 1-2 jumlalik qisqacha ekspert tahlili yoki muxlislarga savol qo'sh (Masalan: "Sizningcha bu transfer o'zini oqlaydimi?").
    4. Faqat Telegram HTML teglari (<b>, <i>) ishlatilsin. Markdown (`**`) ishlatma!
    5. Oxiriga kanal havolasini qo'shma, uni o'zim qo'shaman.
    """
    
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )
        post_text = response.text.strip()
        post_text += f"\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_ID}"
        return post_text
    except Exception as e:
        logging.error(f"Gemini AI xatosi: {e}")
        return f"⚽️ <b>{title}</b>\n\n{summary}\n\n📢 {CHANNEL_ID}"

# ==================== YANGILIKLARNI TEKSHIRISH VA YUBORISH ====================
async def check_and_post_news():
    logging.info("Futbol yangiliklari tekshirilmoqda...")
    for feed_url in RSS_FEEDS:
        try:
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in feed.entries[:3]: # Har bir manbadan eng so'nggi 3 ta xabarni tekshiramiz
                news_id = entry.get("id", entry.get("link", entry.title))
                
                if news_id not in POSTED_NEWS_IDS:
                    POSTED_NEWS_IDS.add(news_id)
                    
                    title = entry.title
                    summary = entry.get("summary", "")
                    
                    # AI ga yuborib post tayyorlaymiz
                    post = await generate_football_post(title, summary)
                    
                    # Kanalga yuboramiz
                    await bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode="HTML")
                    logging.info(f"Yangi post kanalga tashlandi: {title}")
                    
                    # Spam bo'lmasligi uchun xabarlar oralig'ida 5 soniya kutamiz
                    await asyncio.sleep(5)
                    return # Har safar faqat 1 ta eng yangi xabarni chiqaradi
        except Exception as e:
            logging.error(f"RSS xatosi: {e}")

# ==================== BOT HANDLERS ====================
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(f"👋 Salom {message.from_user.full_name}!\n\nMen {CHANNEL_ID} kanali uchun avtomatik futbol xabarlari tayyorlovchi AI botman.")

# ==================== RENDER UCHUN WEB SERVER ====================
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
    
    # Har 30 daqiqada yangiliklarni tekshiradigan Scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_post_news, "interval", minutes=30)
    scheduler.start()
    
    # Bot ishga tushganda darhol 1 marta tekshirsin
    asyncio.create_task(check_and_post_news())
    
    logging.info("Futbol AI Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
