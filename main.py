import os
import asyncio
import logging
import aiohttp
import feedparser
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai

# ==================== SOZLAMALAR ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8530860989:AAFfIgL4OUGUbYctUJAIpz-2j05vun2v9lQ")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Jahon_Chempiyati")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")
PORT = int(os.getenv("PORT", 10000))

CHANNEL_TAG = "@Jahon_Chempiyati"

# Qayta joylamaslik uchun xotira
POSTED_MATCH_IDS = set()
POSTED_NEWS_IDS = set()

# Yangiliklar olinadigan nufuzli manbalar
NEWS_FEEDS = [
    "https://www.skysports.com/rss/12040",          # Transferlar va yangiliklar
    "https://feeds.bbci.co.uk/sport/football/rss.xml", # Rasmiy xabarlar
    "https://www.goal.com/feeds/en/news"           # Katta futbol yangiliklari
]

# Mavzuli rasmlar
IMG_TRANSFER = "https://images.unsplash.com/photo-1522778119026-d647f0596c20?w=1200&auto=format&fit=crop&q=80"
IMG_INJURY = "https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=1200&auto=format&fit=crop&q=80"
IMG_BIRTHDAY = "https://images.unsplash.com/photo-1518091043644-c1d4457512c6?w=1200&auto=format&fit=crop&q=80"
IMG_DEFAULT = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=1200&auto=format&fit=crop&q=80"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ==================== GEMINI AI ====================
ai_client = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY.strip())
        logging.info("Gemini AI muvaffaqiyatli ulandi!")
    except Exception as e:
        logging.error(f"Gemini xatosi: {e}")

# ==================== AI: TRANSFER, JAROHAT VA TUG'ILGAN KUN ====================
async def generate_football_news_post(title: str, summary: str):
    """Futbol xabarini tahlil qilib, o'zbek tilida professional post yaratish"""
    if not ai_client:
        return None, IMG_DEFAULT

    prompt = f"""
    Sen professional futbol jurnalistisan.
    Quyidagi futbol xabarini O'zbek tilida Telegram kanali uchun juda qiziqarli, emotsional qilib yozib ber:
    
    Sarlavha: {title}
    Matn: {summary}
    
    TALABLAR:
    1. Mavzuni aniqlab sarlavha qo'y:
       - Agar transfer yoki shartnoma bo'lsa: "💣 RASMAN / TEZKOR TRANSFER!"
       - Agar jarohat bo'lsa: "🏥 YOMON XABAR: JAROHAT!"
       - Agar tug'ilgan kun bo'lsa: "🎂 BUGUN TAVALLUD AYYOM!"
       - Boshqa muhim yangilik bo'lsa: "⚡️ TEZKOR XABAR!"
    2. Matn 3-4 ta ravon jumlada bo'lsin. Muxlislarga bitta qiziqarli savol qoldir.
    3. Faqat Telegram HTML teglari (<b>, <i>) ishlatilsin.
    4. Hech qanday havola (link), boshqa kanal yoki sayt nomini mutlaqo kiritma!
    5. Faqat o'zbek tilida bo'lsin.
    """
    try:
        res = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )
        clean = [l for l in res.text.strip().split("\n") if "t.me/" not in l and "http" not in l and "@" not in l]
        post_body = "\n".join(clean).strip()
        full_text = f"{post_body}\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"

        # Mavzuga qarab rasm tanlash
        t_lower = title.lower() + " " + summary.lower()
        if "transfer" in t_lower or "sign" in t_lower or "deal" in t_lower:
            selected_img = IMG_TRANSFER
        elif "injur" in t_lower or "surgery" in t_lower or "ruled out" in t_lower:
            selected_img = IMG_INJURY
        elif "birthday" in t_lower or "turns" in t_lower or "born" in t_lower:
            selected_img = IMG_BIRTHDAY
        else:
            selected_img = IMG_DEFAULT

        return full_text[:950] + f"...\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}" if len(full_text) > 1000 else full_text, selected_img
    except Exception as e:
        logging.error(f"Yangilik tayyorlashda xatolik: {e}")
        return None, IMG_DEFAULT

# ==================== YANGILIKLARNI TEKSHIRISH (AVTOPILOT) ====================
async def check_and_post_latest_news():
    """Har 15 daqiqada yangi transfer, jarohat va yangiliklarni tekshirib kanalga chiqaradi"""
    logging.info("Yangi transfer va futbol xabarlari qidirilmoqda...")
    for feed_url in NEWS_FEEDS:
        try:
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in feed.entries[:6]:
                news_id = entry.get("id", entry.get("link", entry.title))
                if news_id not in POSTED_NEWS_IDS:
                    title = entry.title
                    summary = entry.get("summary", "")
                    
                    # Qiziqarli muhim kalit so'zlar filtri
                    keywords = ["transfer", "sign", "deal", "injury", "injured", "ruled out", "birthday", "contract", "sacked", "manager"]
                    content_to_check = (title + " " + summary).lower()
                    
                    if any(k in content_to_check for k in keywords):
                        POSTED_NEWS_IDS.add(news_id)
                        post_text, img_url = await generate_football_news_post(title, summary)
                        
                        if post_text:
                            try:
                                await bot.send_photo(chat_id=CHANNEL_ID, photo=img_url, caption=post_text, parse_mode="HTML")
                                logging.info(f"✅ Yangilik kanalga joylandi: {title}")
                            except Exception:
                                await bot.send_message(chat_id=CHANNEL_ID, text=post_text, parse_mode="HTML")
                            await asyncio.sleep(6)
                            return
        except Exception as e:
            logging.error(f"RSS xatosi: {e}")

# ==================== O'YINLARNI TEKSHIRISH ====================
async def check_finished_matches(force_one: bool = False):
    if not FOOTBALL_DATA_API_KEY:
        return "FOOTBALL_DATA_API_KEY topilmadi!"
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return f"API Status: {resp.status}"
                data = await resp.json()
        for m in data.get("matches", []):
            match_id = m.get("id")
            status = m.get("status")
            if status == "FINISHED" and (match_id not in POSTED_MATCH_IDS or force_one):
                POSTED_MATCH_IDS.add(match_id)
                home = m.get("homeTeam", {}).get("name", "")
                away = m.get("awayTeam", {}).get("name", "")
                comp = m.get("competition", {}).get("name", "Futbol")
                score = m.get("score", {}).get("fullTime", {})
                h_sc = score.get("home", 0)
                a_sc = score.get("away", 0)
                winner = home if h_sc > a_sc else (away if a_sc > h_sc else "DURANG")
                img = m.get("homeTeam", {}).get("crest", "") if winner in [home, "DURANG"] else m.get("awayTeam", {}).get("crest", "")
                if not img or str(img).endswith(".svg"):
                    img = IMG_DEFAULT
                
                header = f"🏆 <b>G'OLIB: «{winner.upper()}»!</b>" if winner != "DURANG" else "🤝 <b>DURANG!</b>"
                caption = f"{header}\n\n⚔️ <b>{home} {h_sc} : {a_sc} {away}</b>\n🏆 {comp}\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"
                try:
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=img, caption=caption, parse_mode="HTML")
                except Exception:
                    await bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="HTML")
                return f"O'yin joylandi: {home} vs {away}"
        return "Yangi o'yin yo'q."
    except Exception as e:
        return f"Xato: {e}"

# ==================== BUYRUQLAR VA MENYU ====================
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡️ Oxirgi O'yin Natijasi")],
            [KeyboardButton(text="🔥 Yangi Xabarni Tekshirish")],
            [KeyboardButton(text="ℹ️ Bot Holati")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"Salom, <b>{message.from_user.first_name}</b>!\n\n"
        f"📢 Kanal: {CHANNEL_TAG}\n\n"
        "Bot to'liq avtopilotda ishlamoqda:\n"
        "• 💣 Rasmiy transferlar va yangiliklar\n"
        "• 🏥 Jarohatlar va safdan chiqishlar\n"
        "• 🎂 Futbolchilarning tavallud ayyomi\n"
        "• ⚡️ Katta o'yinlar tugashi bilan g'olib surati\n\n"
        "Bularning barchasi rasm bilan avtomatik kanalga joylanadi!",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.message(F.text == "🔥 Yangi Xabarni Tekshirish")
async def force_news_cmd(message: types.Message):
    wait_msg = await message.answer("⏳ Dunyo yangiliklari tahlil qilinmoqda...")
    await check_and_post_latest_news()
    await wait_msg.edit_text("✅ Yangiliklar bazasi tekshirildi va kanalga joylandi!")

@dp.message(F.text == "⚡️ Oxirgi O'yin Natijasi")
async def force_match_cmd(message: types.Message):
    wait_msg = await message.answer("⏳ Oxirgi o'yin qidirilmoqda...")
    res = await check_finished_matches(force_one=True)
    await wait_msg.edit_text(res)

@dp.message(F.text == "ℹ️ Bot Holati")
async def status_cmd(message: types.Message):
    await message.answer(
        f"<b>Bot Holati:</b>\n\n"
        f"📢 Kanal: {CHANNEL_TAG}\n"
        f"🤖 AI Modul: {'Ulangan ✅' if ai_client else 'Ulanmagan ❌'}\n"
        "⏰ Monitoring:\n"
        "• O'yin natijalari: Har 5 daqiqada\n"
        "• Transfer, jarohat va yangiliklar: Har 15 daqiqada",
        parse_mode="HTML"
    )

# ==================== RENDER SERVER ====================
async def health_check(request):
    return web.Response(text="Football News & Match Bot is Live 24/7!", status=200)

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

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    # 1. Har 5 daqiqada o'yinlarni tekshiradi
    scheduler.add_job(lambda: check_finished_matches(force_one=False), "interval", minutes=5)
    
    # 2. Har 15 daqiqada transfer, jarohat va tug'ilgan kunlarni tekshirib kanalga chiqaradi
    scheduler.add_job(check_and_post_latest_news, "interval", minutes=15)
    scheduler.start()

    # Bot yoqilganda darhol bitta yangilikni tekshirib ko'rsin
    asyncio.create_task(check_and_post_latest_news())

    logging.info("Barcha avtomatik modullar bilan bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
