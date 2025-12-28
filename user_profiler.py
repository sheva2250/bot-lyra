# user_profiler.py
import json
import os
import asyncio
from datetime import datetime, timedelta
from groq import Groq
from config import GROQ_API_KEY, MODEL_SMART, LOGS_DIR, SYSTEM_PROMPT_SUMMARIZER

# Init Client
client = Groq(api_key=GROQ_API_KEY)


def read_logs_sync(log_files, uid):
    user_interactions = []
    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        log_data = json.loads(line)
                        if str(log_data.get("uid")) == uid:
                            user_interactions.append(f"Q: {log_data['question']} | A: {log_data['answer']}")
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            continue
    return user_interactions


def get_log_filenames_for_past_days(days: int) -> list:
    base_name = "interaction_log_"
    filenames = []
    today = datetime.now()
    for i in range(days):
        date_to_check = today - timedelta(days=i)
        date_str = date_to_check.strftime('%Y-%m-%d')
        filenames.append(os.path.join(LOGS_DIR, f"{base_name}{date_str}.jsonl"))
    return filenames


async def create_user_profile(uid: str, user_name: str) -> str:
    print(f"[Profiler] Memulai pembuatan profil untuk pengguna: {user_name} ({uid})")

    # 1. Baca Log (Bisa diganti baca DB jika mau, tapi file log oke untuk sementara)
    log_files = get_log_filenames_for_past_days(7)
    loop = asyncio.get_running_loop()

    # Jalankan read file di thread terpisah biar gak blocking bot
    user_interactions = await loop.run_in_executor(None, read_logs_sync, log_files, uid)

    if len(user_interactions) < 5:
        return "Belum ada riwayat percakapan yang signifikan."

    # Ambil 50 interaksi terakhir saja biar gak kepanjangan tokennya
    history_text = "\n".join(user_interactions[-50:])

    prompt_content = f"Berikut adalah data percakapan dengan pengguna '{user_name}':\n\n{history_text}"

    try:
        # 2. Generate Profile pakai Groq (70B)
        # Jalankan di executor karena call API Groq itu blocking
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_SUMMARIZER},
                {"role": "user", "content": prompt_content}
            ],
            model=MODEL_SMART,  # Pakai 70B biar analisisnya pinter
            temperature=0.6,
            max_tokens=800
        ))

        print(f"[Profiler] Profil berhasil dibuat untuk {user_name}.")
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[PROFILER ERROR] Gagal saat meringkas profil pengguna: {e}")
        return "Gagal membuat profil pengguna."
