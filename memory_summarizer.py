import google.generativeai as genai
from config import MODEL_NAME

async def summarize_history(history: list) -> str:
    """
    Summarize conversation history.
    Expects history in format: [{"role": "user"/"model", "content": "text"}, ...]
    """
    if not history:
        return ""
    
    text = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in history
    )

    prompt = f"""
Ringkas percakapan berikut menjadi memori jangka panjang.
Simpan fakta penting, preferensi, emosi, dan konteks.
Jangan ulangi kalimat secara verbatim.

Percakapan:
{text}
"""

    try:
        model = genai.GenerativeModel(model_name=MODEL_NAME)
        resp = await model.generate_content_async(prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"[SUMMARIZER ERROR] {e}")
        return ""
