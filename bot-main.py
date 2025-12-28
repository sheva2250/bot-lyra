# bot-main.py
# ==========
# import lib
import discord
import asyncio
import os
import textwrap

from datetime import datetime, timedelta
from discord.ext import commands
from aiohttp import web
from threading import Thread
from groq import Groq

# ==========
# local imports
from config import (
    DISCORD_TOKEN, MASTER_ID, BANNED_USERS, GROQ_API_KEY,
    MODEL_SMART, MODEL_FAST,
    SYSTEM_PROMPT, SYSTEM_PROMPT_MASTER
)
from user_profiler import create_user_profile
from bot_log import log_interaction
from memory_repo import load_history, append_message, delete_old_history
from profile_repo import get_profile, save_profile
# JANGAN LUPA IMPORT init_pool DAN close_pool DI SINI
from db import get_pool, init_pool, close_pool
from memory_summarizer import summarize_history
from memory_summary_repo import save_memory_summary, get_memory_summary

# =========
# global config
print("[System] Booting Lyra with Groq Engine...")

COOLDOWN = 3
PROFILE_TTL_HOURS = 6
MAX_HISTORY = 10
SUMMARY_TRIGGER = 20
KEEP_RECENT = 10

user_cooldowns = {}
local_profile_cache = {}

# =========
# SETUP CLIENT GROQ
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY belum di-set di .env atau config.py!")

client = Groq(api_key=GROQ_API_KEY)

# =========
# DISCORD CLIENT
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========
# CORE AI LOGIC: HYBRID STRATEGY (FAST 8B -> SMART 70B Fallback)
# =========
async def ask_groq(user_question, history, system_prompt):
    messages = [{"role": "system", "content": system_prompt}]

    for chat in history:
        role = "user" if chat['role'] == "user" else "assistant"
        content = ""
        if 'parts' in chat and isinstance(chat['parts'], list):
            content = chat['parts'][0]['text']
        else:
            content = chat.get('content', '')
        if content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_question})

    # --- STRATEGI: SPEED DEMON ---
    # Prioritas 1: Llama 3 8B (Super Cepat)
    try:
        loop = asyncio.get_running_loop()
        completion = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            model=MODEL_FAST,  # <--- UTAMA: 8B
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        ))
        return completion.choices[0].message.content

    except Exception as e:
        # Prioritas 2: Llama 3 70B (Backup Pintar)
        print(f"[GROQ 8B ERROR] Switch to 70B Backup... ({e})")
        try:
            loop = asyncio.get_running_loop()
            completion = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                model=MODEL_SMART,  # <--- BACKUP: 70B
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            ))
            return completion.choices[0].message.content
        except Exception as e2:
            print(f"[GROQ CRITICAL] Dua-duanya error! {e2}")
            return None

# =========
# Keep-alive server
async def handle(request):
    return web.Response(text="Lyra (Groq Edition) is alive.")

app = web.Application()
app.router.add_get("/", handle)

def run_server():
    web.run_app(app, port=int(os.environ.get("PORT", 8080)), handle_signals=False)

Thread(target=run_server, daemon=True).start()

# =========
# Events
@bot.event
async def on_ready():
    # Pastikan DB init dipanggil di sini!
    try:
        await init_pool()
        print("[DB] Connection pool initialized")
    except Exception as e:
        print(f"[DB ERROR] Failed to initialize pool: {e}")

    print("-" * 50)
    print(f"Bot online: {bot.user}")
    print(f"Engine: Groq Hybrid (Primary: {MODEL_FAST})")
    print("-" * 50)

@bot.event
async def on_message(message):
    if message.author.bot or message.author == bot.user:
        return
    if message.author.id in BANNED_USERS:
        return
    if bot.user not in message.mentions:
        await bot.process_commands(message)
        return

    # Setup & Cooldown
    uid = str(message.author.id)
    now = datetime.now()

    if message.author.id != MASTER_ID:
        if uid in user_cooldowns and (now - user_cooldowns[uid]).total_seconds() < COOLDOWN:
            return
        user_cooldowns[uid] = now

    # Clean Content
    content = message.content
    for m in message.mentions:
        content = content.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
    user_question = content.strip()
    if not user_question:
        return

    user_name = message.author.name
    print(f"[MSG] {user_name}: {user_question}")

    # Profiling Logic (RAM -> DB -> Create)
    user_summary = ""
    if uid in local_profile_cache:
        cached = local_profile_cache[uid]
        if now - cached['time'] < timedelta(hours=PROFILE_TTL_HOURS):
            user_summary = cached['summary']

    if not user_summary:
        try:
            row = await get_profile(uid)
            if row:
                last_updated = row["last_updated"]
                now_aware = datetime.now(last_updated.tzinfo) if last_updated.tzinfo else datetime.now()
                if now_aware - last_updated < timedelta(hours=PROFILE_TTL_HOURS):
                    user_summary = row["summary"]
                    local_profile_cache[uid] = {'summary': user_summary, 'time': now}
        except Exception: pass

    if not user_summary:
        try:
            summary = await create_user_profile(uid, user_name)
            if summary and "Belum ada" not in summary:
                asyncio.create_task(save_profile(uid, summary))
                user_summary = summary
                local_profile_cache[uid] = {'summary': summary, 'time': now}
        except Exception: pass

    # Context
    system_prompt = SYSTEM_PROMPT_MASTER if message.author.id == MASTER_ID else SYSTEM_PROMPT
    if user_summary:
        system_prompt += f"\n\n# Info User:\n{user_summary}"
    try:
        memory_summary = await get_memory_summary(uid)
        if memory_summary:
            system_prompt += f"\n\n# Ringkasan Percakapan Sebelumnya:\n{memory_summary}"
    except Exception: pass
    system_prompt += f"\n\n[SYSTEM INFO: Waktu sekarang {now.strftime('%A, %d %B %Y, %H:%M WIB')}]"

    # History Load
    history = []
    try:
        history = await load_history(uid) or []
        if len(history) > SUMMARY_TRIGGER:
            old_part = history[:-KEEP_RECENT]
            old_part_formatted = [{"role": h["role"], "content": h["parts"][0]["text"]} for h in old_part]
            async def background_summarize():
                try:
                    summary = await summarize_history(old_part_formatted)
                    await save_memory_summary(uid, summary)
                    await delete_old_history(uid, keep_last=KEEP_RECENT)
                except Exception as e:
                    print(f"[BG SUMMARIZE ERROR] {e}")
            asyncio.create_task(background_summarize())
            history = history[-KEEP_RECENT:]
    except Exception as e:
        print(f"[HISTORY ERROR] {e}")

    # Generate & Reply
    async with message.channel.typing():
        try:
            ai_answer = await ask_groq(user_question, history, system_prompt)
            if ai_answer is None:
                ai_answer = "Aduh, Ly lagi pusing banget... (Server Groq Error)"

            def sanitize(t):
                return t.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
            ai_answer_clean = sanitize(ai_answer)
            allowed = discord.AllowedMentions(everyone=False, roles=False, users=True)

            for i in range(0, len(ai_answer_clean), 1900):
                await message.reply(ai_answer_clean[i:i + 1900], mention_author=False, allowed_mentions=allowed)

            async def background_save_task():
                try:
                    await append_message(uid, "user", user_question)
                    await append_message(uid, "model", ai_answer)
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, log_interaction, uid, user_name, user_question, ai_answer)
                except Exception as e:
                    print(f"[BG SAVE ERROR] {e}")
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
        if uid in local_profile_cache: del local_profile_cache[uid]
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM conversation_history WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM memory_summaries WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM user_profiles WHERE user_id=$1", uid)
        await ctx.send("Ingatan Lyra tentangmu sudah dihapus.")
    except Exception as e:
        print(f"[RESET ERROR] {e}")
        await ctx.send("Gagal.")

@bot.event
async def on_close():
    # Pastikan DB close dipanggil!
    await close_pool()
    print("[DB] Connection pool closed")

if __name__ == "__main__":
    if not DISCORD_TOKEN: raise RuntimeError("DISCORD_TOKEN Missing")
    bot.run(DISCORD_TOKEN)
