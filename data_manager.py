# di data_manager.py
import json
import os
import shutil

# save dictionary ke file JSON
def save_data(data, filename):
    temp_filename = filename + ".tmp"
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        # 1. Tulis ke file .tmp dulu
        with open(temp_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        # 2. Kalau sukses nulis, baru ganti (overwrite) file asli
        shutil.move(temp_filename, filename)
        return True
    except Exception as e:
        print(f"[ERROR] Gagal menyimpan data ke {filename}: {e}")
        # Hapus file temp jika ada error biar ga nyampah
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return False

# load data dari file JSON yang dibuat
def load_data(filename):
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"[ERROR] Gagal memuat data dari {filename}: {e}")
    return {}
