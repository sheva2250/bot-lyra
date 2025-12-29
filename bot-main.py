# bot-main.py
# ==========
# import lib
import discord
import google.generativeai as genai
import asyncio
import textwrap
import os

from google.api_core import exceptions as google_exceptions
from datetime import datetime, timedelta
from discord.ext import commands
from aiohttp import web
from threading import Thread

# ==========
# local imports
from config import (
    API_KEY_POOL, DISCORD_TOKEN, MASTER_ID, BANNED_USERS,
    MODEL_NAME, SYSTEM_PROMPT, SYSTEM_PROMPT_MASTER, generation_config
)
from user_profiler import create_user_profile
from bot_log import log_interaction
from memory_repo import load_history, append_message, delete_old_history
from profile_repo import get_profile, save_profile
# PENTING: Import DB management
from db import get_pool, init_pool, close_pool
from memory_summarizer import summarize_history
from memory_summary_repo import save_memory_summary, get_memory_summary

# =========
# global config
print(f"[System] Booting Lyra with Gemini Engine ({MODEL_NAME})...")
print(f"[System] Optimization: RAM Cache & Fire-Forget ENABLED")

COOLDOWN = 4
PROFILE_TTL_HOURS = 6
MAX_HISTORY = 10
SUMMARY_TRIGGER = 20
KEEP_RECENT = 10

user_cooldowns = {}

# [OPTIMASI 1] RAM CACHE
# Kita simpan data profil & summary di memori biar gak bolak-balik DB
local_profile_cache = {} 
local_memory_cache = {}

# =========
# DISCORD CLIENT
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========
# GEMINI KEY ROTATION LOGIC
# =========
async def key_rotation(user_question, history, system_prompt):
    # Coba putar kunci sampai berhasil
    for i in range(len(API_KEY_POOL)):
        current_key = API_KEY_POOL[0]
        try:
            # 1. Configure dengan key saat ini
            genai.configure(api_key=current_key)

            # 2. Init Model
            model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                system_instruction=system_prompt,
                generation_config=generation_config
            )

            # 3. Kirim Chat (Non-blocking via executor biar bot gak macet)
            loop = asyncio.get_running_loop()
            
            def call_gemini():
                chat = model.start_chat(history=history)
                response = chat.send_message(user_question)
                return response.text

            ai_answer = await loop.run_in_executor(None, call_gemini)
            return ai_answer

        except google_exceptions.ResourceExhausted:
            print(f"[LIMIT] Key ...{current_key[-5:]} habis! Rotasi ke key berikutnya.")
            API_KEY_POOL.rotate(-1) # Pindah ke key belakang
            await asyncio.sleep(1) # Istirahat sebentar

        except Exception as e:
            print(f"[GEMINI ERROR] {e}")
            if "429" in str(e): # Kalau error limit lain
                API_KEY_POOL.rotate(-1)
                await asyncio.sleep(1)
            else:
                return None # Error fatal lain

    return None # Semua key habis

# =========
# Keep-alive server
async def handle(request):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return web.Response(text="Lyra is alive.")
    except Exception as e:
        return web.Response(text=f"DB Error: {e}", status=500)

app = web.Application()
app.router.add_get("/", handle)

def run_server():
    web.run_app(app, port=int(os.environ.get("PORT", 8080)), handle_signals=False)

Thread(target=run_server, daemon=True).start()

# =========
# Events
@bot.event
async def on_ready():
    # Init Database Pool
    try:
        await init_pool()
        print("[DB] Connection pool initialized")
    except Exception as e:
        print(f"[DB ERROR] Failed to initialize pool: {e}")

    print("-" * 50)
    print(f"Bot online: {bot.user}")
    print(f"Model: {MODEL_NAME}")
    print("-" * 50)

@bot.event
async def on_message(message):
    if message.author.bot or message.author == bot.user: return
    if message.author.id in BANNED_USERS: return
    if bot.user not in message.mentions:
        await bot.process_commands(message)
        return

    # Cooldown
    uid = str(message.author.id)
    now = datetime.now()
    if message.author.id != MASTER_ID:
        if uid in user_cooldowns and (now - user_cooldowns[uid]).total_seconds() < COOLDOWN: return
        user_cooldowns[uid] = now

    # Clean Content
    content = message.content
    for m in message.mentions:
        content = content.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
    user_question = content.strip()
    if not user_question: return

    user_name = message.author.name
    print(f"[MSG] {user_name}: {user_question}")

    # =====================================================
    # [OPTIMASI 1] PROFILING & CONTEXT (RAM FIRST STRATEGY)
    # =====================================================
    
    user_summary = ""
    
    # 1. Cek RAM Cache (User Profile)
    if uid in local_profile_cache:
        cached = local_profile_cache[uid]
        # Validasi TTL (misal 6 jam)
        if now - cached['time'] < timedelta(hours=PROFILE_TTL_HOURS):
            user_summary = cached['summary']
    
    # 2. Kalau gak ada di RAM, Cek DB
    if not user_summary:
        try:
            row = await get_profile(uid)
            if row:
                if datetime.now(row["last_updated"].tzinfo) - row["last_updated"] < timedelta(hours=PROFILE_TTL_HOURS):
                    user_summary = row["summary"]
                    # SIMPAN KE RAM
                    local_profile_cache[uid] = {'summary': user_summary, 'time': now}
        except Exception: pass

    # 3. Kalau gak ada di DB, Generate Baru
    if not user_summary:
        try:
            summary = await create_user_profile(uid, user_name)
            if summary and "Belum ada" not in summary:
                asyncio.create_task(save_profile(uid, summary))
                user_summary = summary
                local_profile_cache[uid] = {'summary': summary, 'time': now}
        except Exception: pass

    # Construct System Prompt
    system_prompt = SYSTEM_PROMPT_MASTER if message.author.id == MASTER_ID else SYSTEM_PROMPT
    if user_summary: system_prompt += f"\n\n# Info User:\n{user_summary}"
    
    # [OPTIMASI 1 LANJUTAN] RAM CACHE (Memory Summary)
    memory_summary = ""
    
    # Cek RAM dulu
    if uid in local_memory_cache:
        # Anggap memory cache valid 1 jam
        if now - local_memory_cache[uid]['time'] < timedelta(hours=1):
            memory_summary = local_memory_cache[uid]['data']
            
    # Kalau gak ada, ambil DB
    if not memory_summary:
        try:
            memory_summary = await get_memory_summary(uid)
            if memory_summary:
                # Simpan RAM
                local_memory_cache[uid] = {'data': memory_summary, 'time': now}
                system_prompt += f"\n\n# Ringkasan Percakapan Sebelumnya:\n{memory_summary}"
        except Exception: pass
    else:
        system_prompt += f"\n\n# Ringkasan Percakapan Sebelumnya:\n{memory_summary}"
        
    system_prompt += f"\n\n[SYSTEM INFO: Waktu sekarang {now.strftime('%A, %d %B %Y, %H:%M WIB')}]"

    # Load History (Tetap dari DB tapi query sudah di-limit)
    history = await load_history(uid) or []
    
    # Background Summarizer
    if len(history) > SUMMARY_TRIGGER:
        old_part = history[:-KEEP_RECENT]
        async def background_summarize():
            try:
                summary = await summarize_history(old_part) 
                await save_memory_summary(uid, summary)
                # Update Cache RAM juga biar sinkron
                local_memory_cache[uid] = {'data': summary, 'time': datetime.now()}
                await delete_old_history(uid, keep_last=KEEP_RECENT)
            except Exception as e: print(f"[BG SUMMARIZE ERROR] {e}")
        asyncio.create_task(background_summarize())
        history = history[-KEEP_RECENT:]

    # Generate Answer
    async with message.channel.typing():
        try:
            # Panggil Gemini
            ai_answer = await key_rotation(user_question, history, system_prompt)

            if ai_answer is None:
                ai_answer = "Maaf, Ly lagi 'pusing' (Limit server habis semua). Coba lagi nanti ya!"

            # Sanitize output
            def sanitize(t): return t.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
            ai_answer_clean = sanitize(ai_answer)
            allowed = discord.AllowedMentions(everyone=False, roles=False, users=True)

            # =====================================================
            # [OPTIMASI 2] FIRE & FORGET
            # Reply DULUAN, Save BELAKANGAN
            # =====================================================
            
            # 1. REPLY KE DISCORD SEKARANG
            for i in range(0, len(ai_answer_clean), 1900):
                await message.reply(ai_answer_clean[i:i+1900], mention_author=False, allowed_mentions=allowed)

            # 2. SAVE DATABASE DI BACKGROUND (User gak nunggu ini)
            async def background_save_task():
                try:
                    await append_message(uid, "user", user_question)
                    await append_message(uid, "model", ai_answer)
                    log_interaction(uid, user_name, user_question, ai_answer)
                except Exception as e: print(f"[BG SAVE ERROR] {e}")
            
            asyncio.create_task(background_save_task())

        except Exception as e:
            print("[ERROR Main Loop]", e)
            await message.reply("Terjadi kesalahan sistem.", mention_author=False)

    await bot.process_commands(message)

# =========
# Commands & Cleanup
@bot.command()
async def reset(ctx):
    try:
        pool = await get_pool()
        uid = str(ctx.author.id)
        
        # HAPUS CACHE RAM JUGA
        if uid in local_profile_cache: del local_profile_cache[uid]
        if uid in local_memory_cache: del local_memory_cache[uid]
        
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM conversation_history WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM memory_summaries WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM user_profiles WHERE user_id=$1", uid)
        await ctx.send("Ingatan Lyra tentangmu sudah dihapus.")
    except Exception as e: await ctx.send("Gagal.")

@bot.event
async def on_close():
    await close_pool()
    print("[DB] Connection pool closed")

if __name__ == "__main__":
    if not DISCORD_TOKEN: raise RuntimeError("DISCORD_TOKEN Missing")
    bot.run(DISCORD_TOKEN)

