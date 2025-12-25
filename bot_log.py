import json
import os
from datetime import datetime
from config import LOGS_DIR


def get_todays_log_file():
    today_str = datetime.now().strftime('%Y-%m-%d')
    # Combine path folder dengan nama file
    return os.path.join(LOGS_DIR, f"interaction_log_{today_str}.jsonl")

# catat interaksi ke log harian
def log_interaction(user_id, user_name, question, answer):
    # make sure folder 'data/logs' ada
    os.makedirs(LOGS_DIR, exist_ok=True)

    log_file_name = get_todays_log_file()

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "user_name": user_name,
        "question": question,
        "answer": answer
    }
    try:
        with open(log_file_name, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[ERROR] Gagal menulis ke file log '{log_file_name}': {e}")