import os
import asyncio
import logging
import aiohttp
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
POSTED_MATCH_IDS = set()

# Mashhur TOP klublar
TOP_TEAMS = [
    "Real Madrid", "Barcelona", "Atletico", "Manchester City", "Liverpool",
    "Arsenal", "Manchester United", "Chelsea", "Tottenham", "Bayern",
    "Dortmund", "Juventus", "Inter", "Milan", "PSG", "Bayer Leverkusen"
]

LEAGUES = {
    "PL": {"name": "APL", "full": "Angliya Premyer-ligasi"},
    "PD": {"name": "La Liga", "full": "Ispaniya La Ligasi"},
    "CL": {"name": "YeChL", "full": "Chempionlar Ligasi"}
}

# Sifatli mavzuli zaxira rasmlar
IMG_MATCH = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=1200&auto=format&fit=crop&q=80"
IMG_STANDINGS = "https://images.unsplash.com/photo-1522778119026-d647f0596c20?w=1200&auto=format&fit=crop&q=80"
IMG_SCORERS = "https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=1200&auto=format&fit=crop&q=80"
IMG_SCHEDULE = "https://images.unsplash.com/photo-1518091043644-c1d4457512c6?w=1200&auto=format&fit=crop&q=80"

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
        logging.error(f"Gemini ulanish xatoligi: {e}")

# ==================== POST MATNLARI VA STATISTIKA ====================
async def generate_match_caption(home_team: str, away_team: str, home_score: int, away_score: int, competition: str, winner_team: str) -> str:
    header = "<b>DURANG! KUCHLAR TENG KELDI!</b>" if winner_team == "DURANG" else f"<b>G'OLIB: «{winner_team.upper()}»!</b>"
    fallback = (
        "<b>O'YIN YAKUNLANDI!</b>\n\n"
        f"<b>Musobaqa:</b> {competition}\n"
        f"<b>{home_team} {home_score} : {away_score} {away_team}</b>\n"
        f"{header}\n\n"
        f"<b>Bizning kanal:</b> {CHANNEL_TAG}"
    )
    if not ai_client:
        return fallback

    prompt = f"""
    Sen professional futbol sharhlovchisisan.
    Hozirgina yakunlangan o'yin uchun Telegram foto-posti matnini tayyorla:
    Musobaqa: {competition}
    O'yin: {home_team} ({home_score}) vs ({away_score}) {away_team}
    G'olib: {winner_team}
    
    1. G'olib jamoaning kuchi, o'yindagi burilish nuqtasi va kim qahramon bo'lganiga 2-3 jumlada qizg'in baho ber.
    2. Muxlislarga bitta qiziqarli savol qoldir.
    3. Faqat Telegram HTML teglari (<b>, <i>) ishlatilsin. 550 ta belgidan oshmasin.
    4. Begona kanal, havola yoki bot nomlarini mutlaqo kiritma! Sof o'zbek tilida yoz.
    """
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )
        clean_text = response.text.strip()
        lines = [l for l in clean_text.split("\n") if "t.me/" not in l and "http" not in l and "@" not in l]
        full_text = f"{header}\n\n{chr(10).join(lines).strip()}\n\n<b>Bizning kanal:</b> {CHANNEL_TAG}"
        return full_text[:950] + f"...\n\n<b>Bizning kanal:</b> {CHANNEL_TAG}" if len(full_text) > 1000 else full_text
    except Exception:
        return fallback

async def fetch_standings_text(league_code: str) -> str:
    if not FOOTBALL_DATA_API_KEY:
        return ""
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
        standings = data.get("standings", [])
        if not standings:
            return ""
        table = standings[0].get("table", [])
        league_info = LEAGUES.get(league_code, {"full": "Turnir"})
        
        text = f"<b>{league_info['full'].upper()} TURNIR JADVALI (Top-6)</b>\n\n"
        text += "<code>O'r  Jamoa           O'y  Farq  Och</code>\n"
        text += "<code>------------------------------------</code>\n"
        for item in table[:6]:
            pos = item.get("position")
            team = item.get("team", {}).get("shortName", item.get("team", {}).get("name", ""))[:14]
            played = item.get("playedGames")
            diff = item.get("goalDifference")
            points = item.get("points")
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            text += f"<b>{pos:<2}</b> {team:<15} {played:<4} {diff_str:<5} <b>{points}</b>\n"
        text += f"\n<b>Bizning kanal:</b> {CHANNEL_TAG}"
        return text
    except Exception:
        return ""

async def fetch_scorers_text(league_code: str) -> str:
    if not FOOTBALL_DATA_API_KEY:
        return ""
    url = f"https://api.football-data.org/v4/competitions/{league_code}/scorers?limit=5"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
        scorers = data.get("scorers", [])
        if not scorers:
            return ""
        league_info = LEAGUES.get(league_code, {"full": "Turnir"})
        text = f"<b>{league_info['full'].upper()} ENG YAXSHI TO'PURARLARI</b>\n\n"
        for idx, sc in enumerate(scorers[:5], 1):
            player = sc.get("player", {}).get("name", "Noma'lum")
            team = sc.get("team", {}).get("shortName", sc.get("team", {}).get("name", ""))
            goals = sc.get("goals", 0)
            assists = sc.get("assists") or 0
            text += f"<b>{idx}. {player}</b> ({team})\n   ⚽️ Gollar: <b>{goals}</b> | 🎯 Assist: {assists}\n\n"
        text += f"<b>Bizning kanal:</b> {CHANNEL_TAG}"
        return text
    except Exception:
        return ""

async def fetch_today_matches_text() -> str:
    if not FOOTBALL_DATA_API_KEY:
        return ""
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
        matches = data.get("matches", [])
        top_matches = []
        for m in matches:
            home = m.get("homeTeam", {}).get("name", "")
            away = m.get("awayTeam", {}).get("name", "")
            if any(t.lower() in home.lower() or t.lower() in away.lower() for t in TOP_TEAMS):
                top_matches.append(m)
        if not top_matches:
            return ""
        text = "<b>BUGUNGI KATTA O'YINLAR ANANSI (Toshkent vaqti):</b>\n\n"
        for m in top_matches[:6]:
            home = m.get("homeTeam", {}).get("shortName", m.get("homeTeam", {}).get("name", ""))
            away = m.get("awayTeam", {}).get("shortName", m.get("awayTeam", {}).get("name", ""))
            comp = m.get("competition", {}).get("name", "Futbol")
            utc_time = m.get("utcDate", "")
            time_str = "Vaqti noaniq"
            if utc_time:
                try:
                    dt = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
                    tashkent_hour = (dt.hour + 5) % 24
                    time_str = f"{tashkent_hour:02d}:{dt.minute:02d}"
                except Exception:
                    pass
            text += f"🏆 <b>{comp}</b>\n⚔️ <b>{home} — {away}</b>\n⏰ Boshlanish vaqti: <b>{time_str}</b>\n\n"
        text += f"<b>Bizning kanal:</b> {CHANNEL_TAG}"
        return text
    except Exception:
        return ""

# ==================== AVTOMATIK MONITORING FUNKSIYALARI ====================
async def check_and_post_finished_matches(force_post_one: bool = False):
    """Har 5 daqiqada o'yin tugashini kuzatib, g'olib jamoa surati bilan chiqaradi"""
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
            if status == "FINISHED" and (match_id not in POSTED_MATCH_IDS or force_post_one):
                home = m.get("homeTeam", {}).get("name", "")
                away = m.get("awayTeam", {}).get("name", "")
                comp = m.get("competition", {}).get("name", "Futbol")
                is_top = any(t.lower() in home.lower() or t.lower() in away.lower() for t in TOP_TEAMS)
                if is_top or force_post_one:
                    POSTED_MATCH_IDS.add(match_id)
                    score = m.get("score", {}).get("fullTime", {})
                    h_sc = score.get("home", 0)
                    a_sc = score.get("away", 0)
                    
                    # G'olibni va uning suratini aniqlash
                    if h_sc > a_sc:
                        winner = home
                        winner_img = m.get("homeTeam", {}).get("crest", "")
                    elif a_sc > h_sc:
                        winner = away
                        winner_img = m.get("awayTeam", {}).get("crest", "")
                    else:
                        winner = "DURANG"
                        winner_img = m.get("homeTeam", {}).get("crest", "")
                        
                    if not winner_img or str(winner_img).endswith(".svg"):
                        winner_img = IMG_MATCH
                        
                    caption = await generate_match_caption(home, away, h_sc, a_sc, comp, winner)
                    try:
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=winner_img, caption=caption, parse_mode="HTML")
                    except Exception:
                        await bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="HTML")
                    return f"O'yin joylandi: {home} vs {away}"
        return "Yangi tugagan o'yin yo'q."
    except Exception as e:
        return f"Xatolik: {e}"

async def auto_post_morning_standings():
    """Har kuni ertalab soat 08:30 da jadvalni rasm bilan chiqaradi"""
    for code in ["PL", "PD"]:
        text = await fetch_standings_text(code)
        if text:
            try:
                await bot.send_photo(chat_id=CHANNEL_ID, photo=IMG_STANDINGS, caption=text, parse_mode="HTML")
                await asyncio.sleep(5)
            except Exception:
                pass

async def auto_post_noon_scorers():
    """Har kuni soat 12:00 da to'purarlarni rasm bilan chiqaradi"""
    text = await fetch_scorers_text("PL")
    if text:
        try:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=IMG_SCORERS, caption=text, parse_mode="HTML")
        except Exception:
            pass

async def auto_post_evening_schedule():
    """Har kuni soat 17:00 da o'yinlar anonsini rasm bilan chiqaradi"""
    text = await fetch_today_matches_text()
    if text:
        try:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=IMG_SCHEDULE, caption=text, parse_mode="HTML")
        except Exception:
            pass

# ==================== BOT BUYRUQLARI VA TUGMALAR ====================
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡️ Oxirgi O'yin Natijasini Joylash")],
            [KeyboardButton(text="📊 Turnir Jadvali"), KeyboardButton(text="🎯 To'purarlar Ro'yxati")],
            [KeyboardButton(text="📅 Bugungi O'yinlar"), KeyboardButton(text="ℹ️ Bot Holati")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"Salom, <b>{message.from_user.first_name}</b>!\n\n"
        f"📢 Kanal: {CHANNEL_TAG}\n"
        "Bot to'liq avtopilotda: mashhur o'yinlar tugashi bilan g'olib surati va tahlili bilan avtomat kanalga chiqadi.\n"
        "Quyidagi tugmalar orqali istalgan paytda darhol post chiqarishingiz mumkin:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.message(F.text == "⚡️ Oxirgi O'yin Natijasini Joylash")
async def manual_match(message: types.Message):
    wait_msg = await message.answer("⏳ Oxirgi tugagan o'yin va g'olib surati tahlil qilinmoqda...")
    res = await check_and_post_finished_matches(force_post_one=True)
    await wait_msg.edit_text(res)

@dp.message(F.text == "📊 Turnir Jadvali")
async def manual_standings(message: types.Message):
    wait_msg = await message.answer("⏳ Turnir jadvali tayyorlanmoqda...")
    text = await fetch_standings_text("PL")
    if text:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=IMG_STANDINGS, caption=text, parse_mode="HTML")
        await wait_msg.edit_text("✅ Jadval rasm bilan kanalga chiqarildi!")
    else:
        await wait_msg.edit_text("❌ Ma'lumot olib bo'lmadi.")

@dp.message(F.text == "🎯 To'purarlar Ro'yxati")
async def manual_scorers(message: types.Message):
    wait_msg = await message.answer("⏳ To'purarlar ro'yxati olinmoqda...")
    text = await fetch_scorers_text("PL")
    if text:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=IMG_SCORERS, caption=text, parse_mode="HTML")
        await wait_msg.edit_text("✅ To'purarlar rasm bilan kanalga chiqarildi!")
    else:
        await wait_msg.edit_text("❌ Ma'lumot olib bo'lmadi.")

@dp.message(F.text == "📅 Bugungi O'yinlar")
async def manual_today(message: types.Message):
    wait_msg = await message.answer("⏳ Bugungi o'yinlar anonsi olinmoqda...")
    text = await fetch_today_matches_text()
    if text:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=IMG_SCHEDULE, caption=text, parse_mode="HTML")
        await wait_msg.edit_text("✅ O'yinlar anonsi rasm bilan kanalga chiqarildi!")
    else:
        await wait_msg.edit_text("📅 Bugun yirik o'yinlar rejalashtirilmagan.")

@dp.message(F.text == "ℹ️ Bot Holati")
async def manual_status(message: types.Message):
    await message.answer(
        f"<b>Bot Holati:</b>\n\n"
        f"Kanal: {CHANNEL_TAG}\n"
        f"AI Modul: {'Ulangan ✅' if ai_client else 'Ulanmagan ❌'}\n"
        f"Football API: {'Faol ✅' if FOOTBALL_DATA_API_KEY else 'Kiritilmagan ❌'}\n"
        "Kuzatuv: Har 5 daqiqada tugagan o'yinlar avtomat rasm bilan chiqadi.",
        parse_mode="HTML"
    )

# ==================== RENDER WEB SERVER ====================
async def health_check(request):
    return web.Response(text="Football 24/7 Auto-Post Bot is Live!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def scheduled_match_routine():
    await check_and_post_finished_matches(force_post_one=False)

# ==================== ASOSIY ISHGA TUSHIRISH ====================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()

    # Toshkent vaqti bilan avtomatik reja (Scheduler)
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    
    # 1. Har 5 daqiqada tugagan katta o'yinlarni rasm bilan chiqarish
    scheduler.add_job(scheduled_match_routine, "interval", minutes=5)
    
    # 2. Har kuni ertalab soat 08:30 da jadvallar
    scheduler.add_job(auto_post_morning_standings, "cron", hour=8, minute=30)
    
    # 3. Har kuni soat 12:00 da to'purarlar
    scheduler.add_job(auto_post_noon_scorers, "cron", hour=12, minute=0)
    
    # 4. Har kuni soat 17:00 da o'yinlar anonsi
    scheduler.add_job(auto_post_evening_schedule, "cron", hour=17, minute=0)
    
    scheduler.start()

    logging.info("Bot barcha avtomatik rasm va statistika modullari bilan ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
