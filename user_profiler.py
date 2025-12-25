import json
import os
import asyncio
import google.generativeai as genai
from datetime import datetime, timedelta
from config import MODEL_NAME, SYSTEM_PROMPT_SUMMARIZER, LOGS_DIR # Impor path folder logs

def read_logs_sync(log_files, user_id):
    user_interactions = []
    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        log_data = json.loads(line)
                        if str(log_data.get("user_id")) == user_id:
                            user_interactions.append(f"Q: {log_data['question']} | A: {log_data['answer']}")
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            continue
    return user_interactions

# get path list untuk N hari terakhir
def get_log_filenames_for_past_days(days: int) -> list:
    base_name = "interaction_log_" # set name file
    filenames = []
    today = datetime.now()
    for i in range(days):
        date_to_check = today - timedelta(days=i)
        date_str = date_to_check.strftime('%Y-%m-%d')
        # combine path folder dengan nama file
        filenames.append(os.path.join(LOGS_DIR, f"{base_name}{date_str}.jsonl"))
    return filenames

# define function untuk membuat user profile
async def create_user_profile(user_id: str, user_name: str) -> str:
    print(f"[Profiler] Memulai pembuatan profil untuk pengguna: {user_name} ({user_id})")

    log_files = get_log_filenames_for_past_days(7)
    loop = asyncio.get_running_loop()
    user_interactions = await loop.run_in_executor(None, read_logs_sync, log_files, user_id)

    if len(user_interactions) < 10:
        return "Belum ada riwayat percakapan yang signifikan."

    history_text = "\n".join(user_interactions[-30:])
    prompt_for_summarizer = f"Berikut adalah data percakapan dengan pengguna '{user_name}':\n\n{history_text}"
    try:
        summarizer_model = genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=SYSTEM_PROMPT_SUMMARIZER)
        response = await summarizer_model.generate_content_async(prompt_for_summarizer)
        print(f"[Profiler] Profil berhasil dibuat untuk {user_name}.")
        return response.text
    except Exception as e:
        print(f"[ERROR] Gagal saat meringkas profil pengguna: {e}")
        return "Gagal membuat profil pengguna."