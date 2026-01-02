import json
import os
import shutil

def save_data(data, filename):
    temp_filename = filename + ".tmp"
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(temp_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        shutil.move(temp_filename, filename)
        return True
    except Exception as e:
        print(f"[ERROR] Gagal menyimpan data ke {filename}: {e}")

        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return False

def load_data(filename):
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"[ERROR] Gagal memuat data dari {filename}: {e}")
    return {}
