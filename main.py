import os
import asyncio
import logging
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai

# ==================== SOZLAMALAR ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8530860989:AAFfIgL4OUGUbYctUJAIpz-2j05vun2v9lQ")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Jahon_Chempiyati")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")
PORT = int(os.getenv("PORT", 10000))

CHANNEL_TAG = "@Jahon_Chempiyati"
POSTED_MATCH_IDS = set()

# Mashhur TOP klublar
TOP_TEAMS = [
    "Real Madrid", "Barcelona", "Atletico", "Manchester City", "Liverpool",
    "Arsenal", "Manchester United", "Chelsea", "Tottenham", "Bayern",
    "Dortmund", "Juventus", "Inter", "Milan", "PSG", "Bayer Leverkusen"
]

# Sifatli zaxira futbol rasmi (Telegram 100% qabul qiladi)
DEFAULT_MATCH_IMAGE = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=1200&auto=format&fit=crop&q=80"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ==================== GEMINI AI (YANGI SDK) ====================
ai_client = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY.strip())
        logging.info("✅ Gemini AI mijozi muvaffaqiyatli ulandi!")
    except Exception as e:
        logging.error(f"Gemini ulanishida xatolik: {e}")
else:
    logging.warning("⚠️ GEMINI_API_KEY topilmadi!")

# ==================== AI POST MATNI (CAPTION) ====================
async def generate_match_caption(home_team: str, away_team: str, home_score: int, away_score: int, competition: str, winner_team: str) -> str:
    if winner_team == "DURANG":
        result_header = "🤝 <b>DURANG! KUCHLAR TENG KELDI!</b>"
    else:
        result_header = f"🏆 <b>G'OLIB: «{winner_team.upper()}»!</b>"

    fallback = (
        f"⚡️ <b>O'YIN YAKUNLANDI!</b>\n\n"
        f"🏆 <b>Musobaqa:</b> {competition}\n"
        f"⚔️ <b>{home_team} {home_score} : {away_score} {away_team}</b>\n"
        f"{result_header}\n\n"
        f"⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"
    )

    if not ai_client:
        return fallback

    prompt = f"""
    Sen professional futbol sharhlovchisisan.
    Hozirgina yakunlangan o'yin uchun Telegram foto-posti uchun qisqa matn tayyorla:
    
    Musobaqa: {competition}
    O'yin: {home_team} ({home_score}) vs ({away_score}) {away_team}
    G'olib: {winner_team}
    
    TALABLAR:
    1. Agar g'olib bo'lsa: "🏆 G'OLIB: «{winner_team.upper()}»!" deb sarlavha qo'y.
    2. Agar durang bo'lsa: "🤝 SHIDDATLI DURANG!" deb boshla.
    3. G'olib jamoaning o'yini, kim ajralib turgani va holatiga 2-3 jumlada qizg'in baho ber.
    4. Muxlislarga bitta qiziqarli savol qoldir.
    5. Faqat Telegram HTML teglari (<b>, <i>) ishlatilsin. Matn 600 ta belgidan oshmasin!
    6. Begona kanal, havola yoki bot nomlarini mutlaqo kiritma!
    7. Faqat sof o'zbek tilida yoz.
    """
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )
        clean_text = response.text.strip()
        lines = [l for l in clean_text.split("\n") if "t.me/" not in l and "http" not in l and "@" not in l]
        post_body = "\n".join(lines).strip()
        
        full_text = f"{post_body}\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"
        
        if len(full_text) > 1000:
            full_text = full_text[:950] + f"...\n\n⚽️ <b>Bizning kanal:</b> {CHANNEL_TAG}"
            
        return full_text
    except Exception as e:
        logging.error(f"Gemini xatosi: {e}")
        return fallback

# ==================== O'YINLARNI TEKSHIRISH VA YUBORISH ====================
async def check_finished_matches(is_first_run: bool = False):
    if not FOOTBALL_DATA_API_KEY:
        logging.warning("FOOTBALL_DATA_API_KEY o'rnatilmagan!")
        return

    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    url = "https://api.football-data.org/v4/matches"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logging.warning(f"Matches API status kodi: {resp.status}")
                    return
                data = await resp.json()

        for m in data.get("matches", []):
            match_id = m.get("id")
            status = m.get("status")

            if status == "FINISHED" and match_id not in POSTED_MATCH_IDS:
                home_team = m.get("homeTeam", {}).get("name", "")
                away_team = m.get("awayTeam", {}).get("name", "")
                competition = m.get("competition", {}).get("name", "Futbol")

                is_top = any(t.lower() in home_team.lower() or t.lower() in away_team.lower() for t in TOP_TEAMS)
                
                if is_top:
                    POSTED_MATCH_IDS.add(match_id)

                    if is_first_run:
                        continue

                    score = m.get("score", {}).get("fullTime", {})
                    h_score = score.get("home", 0)
                    a_score = score.get("away", 0)

                    home_crest = m.get("homeTeam", {}).get("crest", "")
                    away_crest = m.get("awayTeam", {}).get("crest", "")

                    if h_score > a_score:
                        winner = home_team
                        winner_image = home_crest
                    elif a_score > h_score:
                        winner = away_team
                        winner_image = away_crest
                    else:
                        winner = "DURANG"
                        winner_image = home_crest

                    # Telegram .svg faylni qabul qilmaydi, PNG/JPG kerak
                    if not winner_image or str(winner_image).endswith(".svg"):
                        winner_image = DEFAULT_MATCH_IMAGE

                    caption = await generate_match_caption(
                        home_team=home_team,
                        away_team=away_team,
                        home_score=h_score,
                        away_score=a_score,
                        competition=competition,
                        winner_team=winner
                    )

                    try:
                        await bot.send_photo(
                            chat_id=CHANNEL_ID,
                            photo=winner_image,
                            caption=caption,
                            parse_mode="HTML"
                        )
                        logging.info(f"✅ G'olib ({winner}) surati bilan post joylandi!")
                    except Exception as img_err:
                        logging.error(f"Rasm bilan yuborishda xatolik ({img_err}), matn yuborilmoqda...")
                        await bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="HTML")

                    await asyncio.sleep(4)
    except Exception as e:
        logging.error(f"O'yinlarni tekshirishda xatolik: {e}")

async def scheduled_match_check():
    await check_finished_matches(is_first_run=False)

# ==================== BUYRUQLAR ====================
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(f"👋 Salom! Men {CHANNEL_TAG} kanali uchun o'yin natijalarini kuzatuvchi botman.")

# ==================== RENDER WEB SERVER ====================
async def health_check(request):
    return web.Response(text="Football Bot is Running 24/7!", status=200)

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

    # 1. Eski o'yinlarni xotiraga olish
    await check_finished_matches(is_first_run=True)

    # 2. Har 5 daqiqada yangi o'yinlarni tekshirish
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(scheduled_match_check, "interval", minutes=5)
    scheduler.start()

    logging.info("Bot to'liq sozlandi va ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
