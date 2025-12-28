# bot-main.py
# ==========
# import lib
import discord
import google.generativeai as genai
import asyncio
import textwrap
import os

from google.api_core import exceptions as google_exceptions
from datetime import datetime, timedelta, timezone
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
from memory_repo import load_history, append_message, trim_history_if_needed, delete_old_history
from profile_repo import get_profile, save_profile
from db import get_pool, init_pool, close_pool
from memory_summarizer import summarize_history
from memory_summary_repo import save_memory_summary, get_memory_summary

# =========
# global config
print("[System] Booting Lyra...")

COOLDOWN = 5
PROFILE_TTL_HOURS = 6
MAX_HISTORY = 10
SUMMARY_TRIGGER = 20
KEEP_RECENT = 10

user_cooldowns = {}

# [OPTIMASI 1] RAM Cache untuk Profil User
# Format: {uid: {'summary': str, 'time': datetime}}
local_profile_cache = {}

# =========
# DISCORD CLIENT
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========
# Gemini Key Rotation
async def key_rotation(user_question, history, system_prompt):
    for i in range(len(API_KEY_POOL)):
        try:
            genai.configure(api_key=API_KEY_POOL[0])

            model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                system_instruction=system_prompt,
                generation_config=generation_config
            )

            chat = model.start_chat(history=history)
            return await chat.send_message_async(user_question)

        except google_exceptions.ResourceExhausted as e:
            print(f"[KEY LIMIT] {e}")

            if i == len(API_KEY_POOL) - 1:
                return None

            await asyncio.sleep(2)
            API_KEY_POOL.rotate(-1)
            print(f"[KEY ROTATION] Switch → {API_KEY_POOL[0][:5]}...")

    return None

# =========
# Keep-alive server (Render)

async def handle(request):
    return web.Response(text="Lyra is alive.")

app = web.Application()
app.router.add_get("/", handle)

def run_server():
    web.run_app(app, port=int(os.environ.get("PORT", 8080)), handle_signals=False)

Thread(target=run_server, daemon=True).start()

# =========
# Events

@bot.event
async def on_ready():
    # Initialize database pool on startup
    try:
        await init_pool()
        print("[DB] Connection pool initialized")
    except Exception as e:
        print(f"[DB ERROR] Failed to initialize pool: {e}")
     
    print("-" * 50)
    print(f"Bot online: {bot.user}")
    print(f"Model: {MODEL_NAME}")
    print("Persona: Lyra")
    print("-" * 50)

@bot.event
async def on_message(message):
    if message.author.bot or message.author == bot.user:
        return

    if message.author.id in BANNED_USERS:
        await message.reply("Maaf, Ly gamau ngobrol sama kamu.", mention_author=False)
        return

    if bot.user not in message.mentions:
        await bot.process_commands(message)
        return

    # =========
    # Cooldown
    uid = str(message.author.id)
    now = datetime.now()

    if message.author.id != MASTER_ID:
        if uid in user_cooldowns and (now - user_cooldowns[uid]).total_seconds() < COOLDOWN:
            return
        user_cooldowns[uid] = now

    # =========
    # Clean mention
    content = message.content
    for m in message.mentions:
        content = content.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
    user_question = content.strip()
    if not user_question:
        return

    user_name = message.author.name
    print(f"[MSG] {user_name}: {user_question}")

    # =========
    # [OPTIMASI 2] Profiling Smart Cache (RAM First -> DB -> Generate)
    user_summary = ""
    
    # 1. Cek RAM (Instan)
    if uid in local_profile_cache:
        cached = local_profile_cache[uid]
        if now - cached['time'] < timedelta(hours=PROFILE_TTL_HOURS):
            user_summary = cached['summary']
    
    # 2. Cek DB (Kalau RAM kosong)
    if not user_summary:
        try:
            row = await get_profile(uid)
            if row:
                last_updated = row["last_updated"]
                # Handle timezone awareness (Postgres usually returns aware datetime)
                now_aware = datetime.now(last_updated.tzinfo) if last_updated.tzinfo else datetime.now()
                
                if now_aware - last_updated < timedelta(hours=PROFILE_TTL_HOURS):
                    user_summary = row["summary"]
                    # Update RAM Cache
                    local_profile_cache[uid] = {'summary': user_summary, 'time': now}
        except Exception as e:
            print(f"[PROFILE DB ERROR] {e}")

    # 3. Generate Baru (Kalau DB juga kosong/expired)
    if not user_summary:
        try:
            summary = await create_user_profile(uid, user_name)
            if summary and "Belum ada" not in summary and "Gagal" not in summary:
                # Fire & Forget Save Profile
                asyncio.create_task(save_profile(uid, summary))
                user_summary = summary
                # Simpan ke RAM biar chat berikutnya ngebut
                local_profile_cache[uid] = {'summary': summary, 'time': now}
        except Exception as e:
            print(f"[PROFILE GEN ERROR] {e}")

    # =========
    # Persona
    system_prompt = SYSTEM_PROMPT_MASTER if message.author.id == MASTER_ID else SYSTEM_PROMPT
    if user_summary:
        system_prompt += f"\n\n# Info User:\n{user_summary}"

    try:
        memory_summary = await get_memory_summary(uid)
        if memory_summary:
            system_prompt += f"\n\n# Ringkasan Percakapan Sebelumnya:\n{memory_summary}"
    except Exception as e:
        print(f"[MEMORY SUMMARY ERROR] {e}")

    system_prompt += f"\n\n[SYSTEM INFO: Waktu sekarang {now.strftime('%A, %d %B %Y, %H:%M WIB')}]"

    # =========
    # Load history
    history = []
    try:
        history = await load_history(uid) or []
        
        # Summarize Logic
        if len(history) > SUMMARY_TRIGGER:
            old_part = history[:-KEEP_RECENT]
            old_part_formatted = [
                {"role": h["role"], "content": h["parts"][0]["text"]}
                for h in old_part
            ]
            
            # Fire & Forget Summarization (Biar gak nunggu)
            async def background_summarize():
                try:
                    summary = await summarize_history(old_part_formatted)
                    await save_memory_summary(uid, summary)
                    await delete_old_history(uid, keep_last=KEEP_RECENT)
                except Exception as e:
                    print(f"[BG SUMMARIZE ERROR] {e}")
            
            asyncio.create_task(background_summarize())

            # Potong history lokal untuk dikirim ke Gemini sekarang
            history = history[-KEEP_RECENT:]
            
    except Exception as e:
        print(f"[HISTORY ERROR] {e}")

    async with message.channel.typing():
        try:
            response = await key_rotation(user_question, history, system_prompt)

            if response is None:
                ai_answer = "Aduh, Ly lagi error internal…"
            else:
                try:
                    ai_answer = response.text
                except ValueError:
                    ai_answer = "Maaf, Ly gabisa jawab itu ya…"

            # =================================================================
            # [OPTIMASI 3] PRIORITAS REPLY & NON-BLOCKING SAVE
            # =================================================================

            # A. KIRIM REPLY KE USER (Prioritas Utama - Langsung)
            def sanitize(t):
                return t.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

            ai_answer_clean = sanitize(ai_answer)
            allowed = discord.AllowedMentions(everyone=False, roles=False, users=True)

            for i in range(0, len(ai_answer_clean), 1900):
                await message.reply(ai_answer_clean[i:i+1900], mention_author=False, allowed_mentions=allowed)

            # B. SAVE DB & LOG DI BACKGROUND (Menggunakan Executor untuk File I/O)
            async def background_save_task():
                try:
                    # 1. Save DB (Async)
                    await append_message(uid, "user", user_question)
                    await append_message(uid, "model", ai_answer)
                    
                    # 2. Save Log File (Blocking I/O) -> Run in Executor
                    # Ini mencegah bot "Freeze" saat menulis file ke disk
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, log_interaction, uid, user_name, user_question, ai_answer)
                    
                except Exception as e:
                    print(f"[BG SAVE ERROR] {e}")

            # Jalankan task di background
            asyncio.create_task(background_save_task())

        except Exception as e:
            print("[ERROR]", e)
            await message.reply("Terjadi kesalahan sistem.", mention_author=False)

    await bot.process_commands(message)

# =========
# Commands

@bot.command()
async def reset(ctx):
    try:
        pool = await get_pool()
        uid = str(ctx.author.id)
        # Clear RAM Cache juga
        if uid in local_profile_cache:
            del local_profile_cache[uid]
            
        async with pool.acquire() as conn:
            # Delete from all tables
            await conn.execute("DELETE FROM conversation_history WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM memory_summaries WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM user_profiles WHERE user_id=$1", uid)
        await ctx.send("Ingatan Lyra tentangmu sudah dihapus.")
    except Exception as e:
        print(f"[RESET ERROR] {e}")
        await ctx.send("Gagal menghapus ingatan. Coba lagi nanti.")

# =========
# Cleanup on shutdown

@bot.event
async def on_close():
    await close_pool()
    print("[DB] Connection pool closed")

# =========
# Run

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN tidak ditemukan")

    bot.run(DISCORD_TOKEN)
