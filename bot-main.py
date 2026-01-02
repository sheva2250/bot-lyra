# ==========
import discord
import asyncio
import os
from datetime import datetime, timedelta
from discord.ext import commands
from aiohttp import web
from threading import Thread

from grok_client import grok_chat

# ==========
# local imports
from config import (
    DISCORD_TOKEN, MASTER_ID, BANNED_USERS,
    MODEL_NAME, SYSTEM_PROMPT, SYSTEM_PROMPT_MASTER
)
from user_profiler import create_user_profile
from bot_log import log_interaction
from memory_repo import load_history, append_message, delete_old_history
from profile_repo import get_profile, save_profile
from db import get_pool
from memory_summarizer import summarize_history
from memory_summary_repo import save_memory_summary, get_memory_summary

# =========
# global config
print(f"[System] Booting Lyra with Grok Engine ({MODEL_NAME})...")
print(f"[System] Optimization: RAM Cache & Fire-Forget ENABLED")

COOLDOWN = 4
PROFILE_TTL_HOURS = 6
SUMMARY_TRIGGER = 20
KEEP_RECENT = 10

user_cooldowns = {}

# RAM CACHE
local_profile_cache = {}
local_memory_cache = {}

# DB Status Flag
db_initialized = False

# =========
# DISCORD CLIENT
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========
# Keep-alive server (Render free-tier)
async def handle(request):
    global db_initialized
    if not db_initialized:
        return web.Response(text="Bot is starting, database not ready yet...", status=503)
    
    try:
        pool = await get_pool()
        if pool is None:
            return web.Response(text="Database pool is None", status=500)
            
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return web.Response(text="Lyra is alive and database is connected.")
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
    global db_initialized
    
    print("-" * 50)
    print(f"Bot logged in as: {bot.user}")
    print("-" * 50)
    
    try:
        print("[DB] Initializing database connection...")
        pool = await init_pool()
        if pool is None:
            print("[DB ERROR] Failed to initialize pool - pool is None")
            print("[DB ERROR] Bot will continue but database features will not work")
        else:
            db_initialized = True
            print("[DB] ✓ Connection pool initialized successfully")
    except Exception as e:
        print(f"[DB ERROR] Failed to initialize pool: {e}")
        print("[DB ERROR] Bot will continue but database features will not work")

    print("-" * 50)
    print(f"Model: {MODEL_NAME}")
    print(f"Database Status: {'✓ Connected' if db_initialized else '✗ Failed'}")
    print("-" * 50)


@bot.event
async def on_message(message):
    global db_initialized
    
    if message.author.bot or message.author == bot.user:
        return
    if message.author.id in BANNED_USERS:
        return
    if bot.user not in message.mentions:
        await bot.process_commands(message)
        return

    raw = message.content.strip().lower()

    # hapus mention bot
    for m in message.mentions:
        raw = raw.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
    raw = raw.strip()

    greeting_set = {"hi", "hello", "halo", "hallo", "hey", "woy", "woi", "p"}

    if raw in greeting_set:
        await message.reply(
            "Halo, nama ku Lyra! kamu bisa panggil aku Ly loh biar keliatan akrab hehe :p",
            mention_author=False
        )
        return

    # Check DB status
    if not db_initialized:
        await message.reply(
            "Maaf, Ly masih dalam proses startup. Database belum siap (｡•́︿•̀｡)",
            mention_author=False
        )
        return

    # Cooldown (non-master) with cleanup
    uid = str(message.author.id)
    now = datetime.now()

    if message.author.id != MASTER_ID:
        if uid in user_cooldowns and (now - user_cooldowns[uid]).total_seconds() < COOLDOWN:
            return
        user_cooldowns[uid] = now
        
        # Cleanup old cooldowns
        if len(user_cooldowns) > 1000:
            cutoff = now - timedelta(minutes=5)
            user_cooldowns = {k: v for k, v in user_cooldowns.items() if v > cutoff}

    # Clean content
    content = message.content
    for m in message.mentions:
        content = content.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
    user_question = content.strip()
    if not user_question:
        return

    user_name = message.author.name
    print(f"[MSG] {user_name}: {user_question}")

    # ============================
    # USER PROFILE (RAM to DB to GEN)
    # ============================
    user_summary = ""

    if uid in local_profile_cache:
        cached = local_profile_cache[uid]
        if now - cached["time"] < timedelta(hours=PROFILE_TTL_HOURS):
            user_summary = cached["summary"]

    if not user_summary:
        try:
            row = await get_profile(uid)
            if row and now - row["last_updated"] < timedelta(hours=PROFILE_TTL_HOURS):
                user_summary = row["summary"]
                local_profile_cache[uid] = {"summary": user_summary, "time": now}
        except Exception as e:
            print(f"[PROFILE ERROR] {e}")

    if not user_summary:
        try:
            summary = await create_user_profile(uid, user_name)
            user_summary = summary
            local_profile_cache[uid] = {"summary": summary, "time": now}
            if summary and "Belum ada" not in summary:
                asyncio.create_task(save_profile(uid, summary))
        except Exception as e:
            print(f"[PROFILE GEN ERROR] {e}")

    # ============================
    # SYSTEM PROMPT BUILD
    # ============================
    system_prompt = SYSTEM_PROMPT
    if message.author.id == MASTER_ID:
        system_prompt += "\n\n" + SYSTEM_PROMPT_MASTER

    if user_summary and "Belum ada" not in user_summary:
        system_prompt += f"\n\n# Info User:\n{user_summary}"

    # ============================
    # MEMORY SUMMARY (RAM to DB)
    # ============================
    memory_summary = ""

    if uid in local_memory_cache:
        if now - local_memory_cache[uid]["time"] < timedelta(hours=1):
            memory_summary = local_memory_cache[uid]["data"]

    if not memory_summary:
        try:
            memory_summary = await get_memory_summary(uid)
            if memory_summary:
                local_memory_cache[uid] = {"data": memory_summary, "time": now}
        except Exception as e:
            print(f"[MEMORY SUMMARY ERROR] {e}")

    if memory_summary:
        system_prompt += f"\n\n# Ringkasan Percakapan Sebelumnya:\n{memory_summary}"

    system_prompt += f"\n\n[SYSTEM INFO: Waktu sekarang {now.strftime('%A, %d %B %Y, %H:%M WIB')}]"

    # ============================
    # LOAD CHAT HISTORY
    # ============================
    history = await load_history(uid) or []

    # ============================
    # BACKGROUND SUMMARIZER
    # ============================
    if len(history) > SUMMARY_TRIGGER:
        old_part = history[:-KEEP_RECENT]

        async def background_summarize():
            try:
                summary = await summarize_history(old_part)
                await save_memory_summary(uid, summary)
                local_memory_cache[uid] = {"data": summary, "time": datetime.now()}
                await delete_old_history(uid, keep_last=KEEP_RECENT)
            except Exception as e:
                print("[BG SUMMARIZE ERROR]", e)

        asyncio.create_task(background_summarize())
        history = history[-KEEP_RECENT:]

    # ============================
    # CALL GROK (NOW ASYNC)
    # ============================
    async with message.channel.typing():
        try:
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_question})

            ai_answer = await grok_chat(
                messages,
                temperature=0.5,
                max_tokens=120
            )

            def sanitize(t):
                return t.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

            ai_answer_clean = sanitize(ai_answer)
            allowed = discord.AllowedMentions(everyone=False, roles=False, users=True)

            for i in range(0, len(ai_answer_clean), 1900):
                await message.reply(
                    ai_answer_clean[i:i + 1900],
                    mention_author=False,
                    allowed_mentions=allowed
                )

            async def background_save():
                try:
                    await append_message(uid, "user", user_question)
                    await append_message(uid, "assistant", ai_answer)
                    log_interaction(uid, user_name, user_question, ai_answer)
                except Exception as e:
                    print("[BG SAVE ERROR]", e)

            asyncio.create_task(background_save())

        except Exception as e:
            print("[ERROR]", e)
            await message.reply("Maaf, Ly lagi ada masalah teknis nih (◞‸◟；)", mention_author=False)

    await bot.process_commands(message)

# =========
# Commands
@bot.command()
async def reset(ctx):
    global db_initialized
    
    if not db_initialized:
        await ctx.send("Database belum siap, coba lagi nanti.")
        return
        
    try:
        pool = await get_pool()
        if pool is None:
            await ctx.send("Database tidak tersedia.")
            return
            
        uid = str(ctx.author.id)

        local_profile_cache.pop(uid, None)
        local_memory_cache.pop(uid, None)

        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM conversation_history WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM memory_summaries WHERE user_id=$1", uid)
            await conn.execute("DELETE FROM user_profiles WHERE user_id=$1", uid)

        await ctx.send("Ingatan Lyra tentangmu sudah dihapus.")
    except Exception as e:
        print(f"[RESET ERROR] {e}")
        await ctx.send("Gagal menghapus data.")

@bot.command()
async def info(ctx):
    help_text = """
**Cara menggunakan Lyra:**
- Tag @Lyra untuk mengobrol
- `!reset` - Hapus ingatan Lyra tentangmu
- `!info` - Tampilkan pesan ini

Lyra akan mengingat percakapanmu dan belajar tentang preferensimu!
    """
    await ctx.send(help_text)

@bot.command()
async def dbstatus(ctx):
    """Check database connection status"""
    global db_initialized
    
    if not db_initialized:
        await ctx.send("Database belum diinisialisasi")
        return
    
    try:
        pool = await get_pool()
        if pool is None:
            await ctx.send("Database pool is None")
            return
            
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            await ctx.send(f"Database connected! Test query result: {result}")
    except Exception as e:
        await ctx.send(f"❌ Database error: {e}")

@bot.event
async def on_close():
    await close_pool()
    print("[DB] Connection pool closed")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN Missing")
    bot.run(DISCORD_TOKEN)

