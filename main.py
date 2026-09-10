import os
import asyncio
import logging
import aiohttp
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
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

TOP_TEAMS = [
    "Real Madrid", "Barcelona", "Atletico", "Manchester City", "Liverpool",
    "Arsenal", "Manchester United", "Chelsea", "Tottenham", "Bayern",
    "Dortmund", "Juventus", "Inter", "Milan", "PSG", "Bayer Leverkusen"
]

LEAGUES = {
    "PL": {"name": "APL", "full": "Angliya Premyer-ligasi"},
    "PD": {"name": "La Liga", "full": "Ispaniya La Ligasi"},
    "SA": {"name": "A Seriya", "full": "Italiya A Seriyasi"},
    "BL1": {"name": "Bundesliga", "full": "Germaniya Bundesligasi"},
    "CL": {"name": "YeChL", "full": "Chempionlar Ligasi"}
}

DEFAULT_MATCH_IMAGE = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=1200&auto=format&fit=crop&q=80"

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
        logging.error(f"Gemini ulanishida xatolik: {e}")

# ==================== TUGMALAR ====================
def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Turnir Jadvali"), KeyboardButton(text="Top-5 Topurarlar")],
            [KeyboardButton(text="Bugungi O'yinlar"), KeyboardButton(text="Oxirgi O'yin Natijasi")],
            [KeyboardButton(text="Bot Holati")]
        ],
        resize_keyboard=True
    )

def get_leagues_inline_kb(action_type: str):
    buttons = []
    row = []
    for code, data in LEAGUES.items():
        row.append(InlineKeyboardButton(text=f"[ {data['name']} ]", callback_data=f"{action_type}_{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== STATISTIKA ====================
async def fetch_standings(league_code: str) -> str:
    if not FOOTBALL_DATA_API_KEY:
        return "FOOTBALL_DATA_API_KEY topilmadi!"
    
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return f"Ma'lumot olishda xatolik: status {resp.status}"
                data = await resp.json()
                
        standings = data.get("standings", [])
        if not standings:
            return "Jadval ma'lumotlari mavjud emas."
            
        table = standings[0].get("table", [])
        league_info = LEAGUES.get(league_code, {"full": "Turnir"})
        
        text = f"<b>{league_info['full'].upper()}</b>\n"
        text += "<b>Turnir jadvali (Top-6):</b>\n\n"
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
    except Exception as e:
        return f"Xatolik yuz berdi: {e}"

async def fetch_top_scorers(league_code: str) -> str:
    if not FOOTBALL_DATA_API_KEY:
        return "FOOTBALL_DATA_API_KEY topilmadi!"
        
    url = f"https://api.football-data.org/v4/competitions/{league_code}/scorers?limit=5"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return f"Topurarlar olishda xatolik: status {resp.status}"
                data = await resp.json()
                
        scorers = data.get("scorers", [])
        if not scorers:
            return "Topurarlar royxati topilmadi."
            
        league_info = LEAGUES.get(league_code, {"full": "Turnir"})
        text = f"<b>{league_info['full'].upper()} TOPURARLARI</b>\n\n"
        
        for idx, sc in enumerate(scorers[:5], 1):
            player = sc.get("player", {}).get("name", "Noma'lum")
            team = sc.get("team", {}).get("shortName", sc.get("team", {}).get("name", ""))
            goals = sc.get("goals", 0)
            assists = sc.get("assists") or 0
            text += f"<b>{idx}. {player}</b> ({team})\n   Gollar: <b>{goals}</b> | Assist: {assists}\n\n"
            
        text += f"<b>Bizning kanal:</b> {CHANNEL_TAG}"
        return text
    except Exception as e:
        return f"Xatolik yuz berdi: {e}"

async def fetch_today_matches() -> str:
    if not FOOTBALL_DATA_API_KEY:
        return "FOOTBALL_DATA_API_KEY topilmadi!"
        
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY.strip()}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return f"O'yinlar jadvalida xatolik: status {resp.status}"
                data = await resp.json()
                
        matches = data.get("matches", [])
        top_matches = []
        
        for m in matches:
            home = m.get("homeTeam", {}).get("name", "")
            away = m.get("awayTeam", {}).get("name", "")
            if any(t.lower() in home.lower() or t.lower() in away.lower() for t in TOP_TEAMS):
                top_matches.append(m)
                
        if not top_matches:
            return f"<b>Bugungi o'yinlar anonsi:</b>\n\nBugun dasturda yirik top jamoalar uchrashuvlari rejalashtirilmagan.\n\n<b>Kanalimiz:</b> {CHANNEL_TAG}"
            
        text = "<b>BUGUNGI ASOSIY O'YINLAR (Toshkent vaqti):</b>\n\n"
        for m in top_matches[:6]:
            home = m.get("homeTeam", {}).get("shortName", m.get("homeTeam", {}).get("name", ""))
            away = m.get("awayTeam", {}).get("shortName", m.get("awayTeam", {}).get("name", ""))
            comp = m.get("competition", {}).get("name", "Futbol")
            utc_time = m.get("utcDate", "")
            
            time_str = ""
            if utc_time:
                try:
                    dt = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
                    tashkent_hour = (dt.hour + 5) % 24
                    time_str = f"{tashkent_hour:02d}:{dt.minute:02d}"
                except Exception:
                    time_str = "Vaqti noaniq"
                    
            status = m.get("status")
            status_badge = f"{time_str}" if status in ["TIMED", "SCHEDULED"] else ("LIVE" if status == "IN_PLAY" else "TUGADI")
            
            text += f"<b>{comp}</b>\n{home} - {away}\nHolat: {status_badge}\n\n"
            
        text += f"<b>Bizning kanal:</b> {CHANNEL_TAG}"
        return text
    except Exception as e:
        return f"Xatolik: {e}"

# ==================== AI CAPTION ====================
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
    Hozirgina yakunlangan o'yin uchun Telegram postiga matn yoz:
    Musobaqa: {competition}
    O'yin: {home_team} ({home_score}) vs ({away_score}) {away_team}
    G'olib: {winner_team}
    
    1. Sarlavhani jiddiy va jozibali qilib yoz.
    2. G'olib jamoaning o'yiniga, kim qahramon bo'lganiga 2-3 jumlada baho ber.
    3. Muxlislarga bitta qiziqarli savol qoldir.
    4. Faqat Telegram HTML teglari (<b>, <i>) ishlatilsin. 600 ta belgidan oshmasin.
    5. Begona havola yoki kanal yozma. Sof o'zbek tilida yoz.
    """
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )
        clean_text = response.text.strip()
        lines = [l for l in clean_text.split("\n") if "t.me/" not in l and "http" not in l and "@" not in l]
        full_text = f"{chr(10).join(lines).strip()}\n\n<b>Bizning kanal:</b> {CHANNEL_TAG}"
        return full_text[:950] + f"...\n\n<b>Bizning kanal:</b> {CHANNEL_TAG}" if len(full_text) > 1000 else full_text
    except Exception:
        return fallback

async def check_finished_matches(force_post_one: bool = False):
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
                    
                    winner = home if h_sc > a_sc else (away if a_sc > h_sc else "DURANG")
                    img = m.get("homeTeam", {}).get("crest", "") if winner in [home, "DURANG"] else m.get("awayTeam", {}).get("crest", "")
                    if not img or str(img).endswith(".svg"):
                        img = DEFAULT_MATCH_IMAGE
                        
                    caption = await generate_match_caption(home, away, h_sc, a_sc, comp, winner)
                    try:
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=img, caption=caption, parse_mode="HTML")
                    except Exception:
                        await bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="HTML")
                        
                    return f"O'yin kanalga chiqarildi: {home} vs {away}"
        return "Hozircha yangi tugagan o'yin topilmadi."
    except Exception as e:
        return f"Xatolik: {e}"

# ==================== HANDLERLAR ====================
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        f"Salom, <b>{message.from_user.first_name}</b>!\n\n"
        f"Kanal: {CHANNEL_TAG}\n"
        "Quyidagi tugmalar orqali kanalga statistika va natijalarni chiqarishingiz mumkin:",
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )

@dp.message(F.text == "Turnir Jadvali")
async def standings_choice(message: types.Message):
    await message.answer("Qaysi liganing turnir jadvalini chiqarmoqchisiz?", reply_markup=get_leagues_inline_kb("std"))

@dp.message(F.text == "Top-5 Topurarlar")
async def scorers_choice(message: types.Message):
    await message.answer("Qaysi liganing topurarlarini kormoqchisiz?", reply_markup=get_leagues_inline_kb("scr"))

@dp.callback_query(F.data.startswith("std_"))
async def post_standings_callback(call: types.CallbackQuery):
    code = call.data.split("_")[1]
    wait_msg = await call.message.edit_text("Turnir jadvali tayyorlanmoqda...")
    text = await fetch_standings(code)
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
        await wait_msg.edit_text(f"Jadval kanalga joylandi!\n\n{text}", parse_mode="HTML")
    except Exception as e:
        await wait_msg.edit_text(f"Kanalga yuborishda xatolik: {e}")

@dp.callback_query(F.data.startswith("scr_"))
async def post_scorers_callback(call: types.CallbackQuery):
    code = call.data.split("_")[1]
    wait_msg = await call.message.edit_text("Topurarlar malumoti olinmoqda...")
    text = await fetch_top_scorers(code)
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
        await wait_msg.edit_text(f"Topurarlar kanalga joylandi!\n\n{text}", parse_mode="HTML")
    except Exception as e:
        await wait_msg.edit_text(f"Kanalga yuborishda xatolik: {e}")

@dp.message(F.text == "Bugungi O'yinlar")
async def today_matches_handler(message: types.Message):
    wait_msg = await message.answer("Bugungi oyinlar jadvali olinmoqda...")
    text = await fetch_today_matches()
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
        await wait_msg.edit_text(f"Kanalga chiqarildi!\n\n{text}", parse_mode="HTML")
    except Exception as e:
        await wait_msg.edit_text(f"Xatolik: {e}")

@dp.message(F.text == "Oxirgi O'yin Natijasi")
async def force_match_handler(message: types.Message):
    wait_msg = await message.answer("Oxirgi oyin qidirilmoqda va AI tahlil tayyorlanmoqda...")
    res = await check_finished_matches(force_post_one=True)
    await wait_msg.edit_text(res)

@dp.message(F.text == "Bot Holati")
async def status_handler(message: types.Message):
    await message.answer(
        f"<b>Bot Statistikasi:</b>\n\n"
        f"Kanal: {CHANNEL_TAG}\n"
        f"AI Modul: {'Ulangan' if ai_client else 'Ulanmagan'}\n"
        f"Football-Data API: {'Faol' if FOOTBALL_DATA_API_KEY else 'Kiritilmagan'}\n"
        "Har 5 daqiqada tugagan yirik oyinlarni avtomat tekshiradi.",
        parse_mode="HTML"
    )

# ==================== RENDER SERVER ====================
async def health_check(request):
    return web.Response(text="Football Stats & Match Bot is Running!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def auto_schedule_routine():
    await check_finished_matches(force_post_one=False)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(auto_schedule_routine, "interval", minutes=5)
    scheduler.start()

    logging.info("Futbol statistika va yangiliklar boti ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
