import json
import os
import asyncio
from datetime import datetime, timedelta

from grok_client import grok_chat
from config import SYSTEM_PROMPT_SUMMARIZER, LOGS_DIR


# =========================
# UTIL: READ LOGS (SYNC)
# =========================
def read_logs_sync(log_files, uid):
    interactions = []

    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        log = json.loads(line)
                        if str(log.get("uid")) == uid:
                            q = log.get("question", "")
                            a = log.get("answer", "")
                            interactions.append(f"User: {q}\nLyra: {a}")
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            continue

    return interactions


def get_log_filenames_for_past_days(days: int) -> list:
    base = "interaction_log_"
    today = datetime.now()
    files = []

    for i in range(days):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        files.append(os.path.join(LOGS_DIR, f"{base}{date_str}.jsonl"))

    return files


# =========================
# MAIN: CREATE USER PROFILE
# =========================
async def create_user_profile(uid: str, user_name: str) -> str:
    print(f"[Profiler] Membuat profil user: {user_name} ({uid})")

    log_files = get_log_filenames_for_past_days(7)
    loop = asyncio.get_running_loop()

    interactions = await loop.run_in_executor(
        None, read_logs_sync, log_files, uid
    )

    if len(interactions) < 10:
        return "Belum ada riwayat percakapan yang signifikan."

    # Batasi supaya token aman
    history_text = "\n\n".join(interactions[-30:])

    prompt = (
        f"Berikut adalah riwayat percakapan dengan pengguna bernama '{user_name}'.\n\n"
        f"{history_text}"
    )

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_SUMMARIZER},
            {"role": "user", "content": prompt},
        ]

        summary = await grok_chat(
            messages,
            temperature=0.3,
            max_tokens=200
        )

        return summary.strip() if summary else "Profil belum dapat dibuat."

    except Exception as e:
        print("[PROFILER ERROR]", e)
        return "Profil belum dapat dibuat."
