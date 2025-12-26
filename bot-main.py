# ==========
# import lib
import discord
import google.generativeai as genai
import asyncio
import textwrap
import collections
import os

from google.api_core import exceptions as google_exceptions
from datetime import datetime, timedelta
from discord.ext import tasks, commands
from aiohttp import web
from threading import Thread

# Pastikan import module lokal kamu benar
from config import (
    API_KEY_POOL, DISCORD_TOKEN, GEMINI_API_KEY, MASTER_ID, BANNED_USERS,
    MODEL_NAME, SYSTEM_PROMPT, SYSTEM_PROMPT_MASTER, generation_config,
    HISTORY_FILE, PROFILES_FILE
)
from user_profiler import create_user_profile
from bot_log import log_interaction
from data_manager import load_data, save_data

# =========
# Config GEMINI
try:
    print("Mengonfigurasi Google Gemini...")
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Gagal mengonfigurasi Gemini: {e}")
    exit()

# global var
print("[System] Memuat data dari disk...")
conversation_histories = load_data(HISTORY_FILE)
user_profiles_cache = load_data(PROFILES_FILE)
user_cooldowns = {}
COOLDOWN = 5

# =========
# DISCORD CLIENT SETUP (HANYA PAKAI SATU: BOT)
intents = discord.Intents.default()
intents.message_content = True

# Gunakan 'bot' saja, tidak perlu 'client_discord'
bot = commands.Bot(command_prefix="!", intents=intents)


# bg task, auto save per 5 mins
@tasks.loop(minutes=5)
async def periodic_save_task():
    print("[System] Menjalankan tugas penyimpanan berkala...")
    save_data(conversation_histories, HISTORY_FILE)
    save_data(user_profiles_cache, PROFILES_FILE)


# =========
# Logic Key Pool

async def key_rotation(chat_session, user_question):
    # Coba sebanyak jumlah kunci yang kita miliki
    for i in range(len(API_KEY_POOL)):
        try:
            # Coba kirim pesan
            response = await chat_session.send_message_async(user_question)
            return response

        except google_exceptions.ResourceExhausted as e:
            error_details = getattr(e, 'error_details', f"({e})")
            print(f"[INFO] Key limit/cold. Detail: {error_details}")

            if i == len(API_KEY_POOL) - 1:
                print("[ERROR] Semua kunci API habis.")
                return None

            # Cold system
            delay = 2
            print(f"[WAITING] Menunggu {delay} detik...")
            await asyncio.sleep(delay)

            # Rotasi kunci
            API_KEY_POOL.rotate(-1)
            new_key = API_KEY_POOL[0]
            print(f"[KEY ROTATION] Ganti ke key: {new_key[:5]}...")

            # Re-configure global key
            genai.configure(api_key=new_key)

            # NOTE: Idealnya chat_session perlu di-rebuild jika key berubah,
            # tapi kita coba global config dulu untuk simplifikasi.

    return None


async def handle(request):
    return web.Response(text="Lyra is alive and running!")

app = web.Application()
app.router.add_get('/', handle)

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, port=port, handle_signals=False)

t = Thread(target=run_server)
t.start()

# =========
# Event & Logic Bot

@bot.event  # Ganti client_discord jadi bot
async def on_ready():
    print("-" * 50)
    print(f'Bot {bot.user} telah online.')  # Ganti client_discord jadi bot
    print('Persona aktif: Lyra')
    print(f'Model AI yang digunakan: {MODEL_NAME}')
    print("-" * 50)
    print(f'Mention @{bot.user.name} untuk berinteraksi.')
    if not periodic_save_task.is_running():
        periodic_save_task.start()


@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:  # Ganti client_discord jadi bot
        return

    # kondisi user ter-banned
    if message.author.id in BANNED_USERS:
        await message.reply("Maaf, Ly gamau ngobrol sama kamu.", mention_author=False)
        return

    # Cek apakah user mention bot
    if bot.user in message.mentions:  # Ganti client_discord jadi bot

        # --- Logic Cooldown ---
        if message.author.id != MASTER_ID:
            current_time = datetime.now()
            user_id_str_for_cooldown = str(message.author.id)

            if user_id_str_for_cooldown in user_cooldowns:
                time_since_last = user_cooldowns[user_id_str_for_cooldown]
                if (current_time - time_since_last).total_seconds() < COOLDOWN:
                    print(f"[System] Spam dari {message.author.name} diabaikan.")
                    return
            user_cooldowns[user_id_str_for_cooldown] = current_time

        # --- Clean Mention & Get Question ---
        cleaned_content = message.content
        for mention in message.mentions:
            cleaned_content = cleaned_content.replace(f'<@{mention.id}>', '').replace(f'<@!{mention.id}>', '')
        user_question = cleaned_content.strip()

        if not user_question:
            return

        print(f"\n[Pesan Diterima] Dari {message.author.name}: {user_question}")

        user_id_str = str(message.author.id)
        user_name = message.author.name

        # --- Profiling Logic ---
        user_summary = ""
        cached_profile = user_profiles_cache.get(user_id_str)
        # (Kode profiling kamu sudah oke, disingkat biar rapi di sini)
        last_updated_time = None
        if cached_profile:
            last_updated_time = datetime.fromisoformat(cached_profile['last_updated'])

        if cached_profile and (datetime.now() - last_updated_time) < timedelta(hours=6):
            user_summary = cached_profile['summary']
        else:
            # Re-fetch profile logic
            user_summary = await create_user_profile(user_id_str, user_name)
            if "Belum ada" not in user_summary and "Gagal" not in user_summary:
                user_profiles_cache[user_id_str] = {'summary': user_summary, 'last_updated': datetime.now().isoformat()}

        # --- Persona Selection ---
        if message.author.id == MASTER_ID:
            active_system_prompt = SYSTEM_PROMPT_MASTER
        else:
            active_system_prompt = SYSTEM_PROMPT
            
        if "Belum ada" not in user_summary and "Gagal" not in user_summary:
            active_system_prompt += f"\n\n# Info User:\n{user_summary}"

        now = datetime.now()
        waktu_str = now.strftime("%A, %d %B %Y, Jam %H:%M WIB")
        active_system_prompt += f"\n\n[SYSTEM INFO: Saat ini adalah {waktu_str}. Ingat ini adalah waktu sekarang.]"
        
        # --- Initiate Model ---
        dynamic_model_gemini = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=active_system_prompt,
            generation_config=generation_config
        )

        # --- History Management ---
        user_history = conversation_histories.setdefault(user_id_str, [])
        MAX_HISTORY = 10
        while len(user_history) > MAX_HISTORY:
            del user_history[:2]  # FIX: Hapus per pasang (User+Model)

        async with message.channel.typing():
            try:
                chat_session = dynamic_model_gemini.start_chat(history=user_history)
                response = await key_rotation(chat_session, user_question)

                # --- FIX: Safety Filter Handling ---
                if response is None:
                    ai_answer = "Aduh, Ly lagi pusing (API Error/Limit)."
                else:
                    # Cek apakah response diblokir oleh Safety Filter
                    try:
                        ai_answer = response.text
                    except ValueError:
                        # Jika response.text error, berarti kena filter
                        print(f"[BLOCKED] Feedback: {response.prompt_feedback}")
                        ai_answer = "Maaf, Ly gabisa jawab itu karena melanggar safety guidelines Google >.<"

                # Log & Save
                log_interaction(user_id_str, user_name, user_question, ai_answer)

                # Simpan history HANYA jika response sukses
                if response and hasattr(response, 'text'):
                    serializable_history = [
                        {'role': msg.role, 'parts': [part.text for part in msg.parts]}
                        for msg in chat_session.history
                    ]
                    conversation_histories[user_id_str] = serializable_history

                # --- Split Message Logic ---
                def sanitize_mass_mentions(text: str) -> str:
                    for m in ("@everyone", "@here"):
                        text = text.replace(m, "@\u200b" + m[1:])
                    return text

                def chunk(text, size=1900):
                    if len(text) <= size:
                        yield text
                        return

                    chunks = textwrap.wrap(text, width=size, break_long_words=False, replace_whitespace=False)
                    for part in chunks:
                        yield part

                ai_answer = sanitize_mass_mentions(ai_answer)
                allowed = discord.AllowedMentions(everyone=False, roles=False, users=True)

                for part in chunk(ai_answer):
                    await message.reply(part, mention_author=False, allowed_mentions=allowed)

            except Exception as e:
                print(f"[ERROR] Bot Crash: {e}")
                await message.reply("Terjadi kesalahan sistem.", mention_author=False)

    # PENTING: Agar command !reset tetap jalan walaupun ada on_message
    await bot.process_commands(message)


# =========
# Commands

@bot.command()
async def reset(ctx):
    user_id = str(ctx.author.id)
    if user_id in conversation_histories:
        del conversation_histories[user_id]
        await ctx.send("Boom! Ingatan tentangmu sudah di-reset~ 🧹")
    else:
        await ctx.send("Kamu belum ada di ingatan Ly kok~")


# =========
# Run Bot & Shutdown
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN tidak ditemukan!")
    else:
        try:
            # GUNAKAN 'bot.run', BUKAN 'client_discord.run'
            bot.run(DISCORD_TOKEN)
        finally:
            print("\n[System] Shutdown initiated...")
            if periodic_save_task.is_running():
                periodic_save_task.cancel()
            save_data(conversation_histories, HISTORY_FILE)
            save_data(user_profiles_cache, PROFILES_FILE)

            print("[System] Data tersimpan. Bye bye!")


