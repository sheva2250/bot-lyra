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
from memory_repo import load_history, append_message, trim_history, delete_old_history
from profile_repo import get_profile, save_profile
from db import get_pool
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
    # Profiling (DB-based, TTL)
    user_summary = ""
    row = await get_profile(uid)

    if row:
        if datetime.now(row["last_updated"].tzinfo) - row["last_updated"] < timedelta(hours=PROFILE_TTL_HOURS):
            user_summary = row["summary"]

    if not user_summary:
        summary = await create_user_profile(uid, user_name)
        if "Belum ada" not in summary and "Gagal" not in summary:
            await save_profile(uid, summary)
            user_summary = summary

    # =========
    # Persona
    system_prompt = SYSTEM_PROMPT_MASTER if message.author.id == MASTER_ID else SYSTEM_PROMPT
    if user_summary:
        system_prompt += f"\n\n# Info User:\n{user_summary}"

    memory_summary = await get_memory_summary(uid)
    if memory_summary:
        system_prompt += f"\n\n# Ringkasan Percakapan Sebelumnya:\n{memory_summary}"

    system_prompt += f"\n\n[SYSTEM INFO: Waktu sekarang {now.strftime('%A, %d %B %Y, %H:%M WIB')}]"

    # =========
    # Load history
    history = await load_history(uid) or []
    if len(history) > SUMMARY_TRIGGER:
        old_part = history[:-KEEP_RECENT]
        summary = await summarize_history(old_part)
        await save_memory_summary(uid, summary)

        await delete_old_history(uid, keep_last=KEEP_RECENT)
        history = history[-KEEP_RECENT:]

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

            await append_message(uid, "user", user_question)
            await append_message(uid, "model", ai_answer)
            await trim_history(uid)

            log_interaction(uid, user_name, user_question, ai_answer)

            def sanitize(t):
                return t.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

            ai_answer = sanitize(ai_answer)
            allowed = discord.AllowedMentions(everyone=False, roles=False, users=True)

            for i in range(0, len(ai_answer), 1900):
                await message.reply(ai_answer[i:i+1900], mention_author=False, allowed_mentions=allowed)

        except Exception as e:
            print("[ERROR]", e)
            await message.reply("Terjadi kesalahan sistem.", mention_author=False)

    await bot.process_commands(message)

# =========
# Commands

@bot.command()
async def reset(ctx):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM conversation_history WHERE user_id=$1", str(ctx.author.id))
    await ctx.send("Ingatan Lyra tentangmu sudah dihapus.")

# =========
# Run

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN tidak ditemukan")

    bot.run(DISCORD_TOKEN)



