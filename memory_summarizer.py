# memory_summarizer.py
from groq import Groq
from config import GROQ_API_KEY, MODEL_FAST  # Kita pakai model yang Cepat (8B)

# Init Client
client = Groq(api_key=GROQ_API_KEY)


async def summarize_history(history: list) -> str:
    """
    Summarize conversation history using Groq (Llama 3).
    Expects history in format: [{"role": "user"/"model", "content": "text"}, ...]
    """
    if not history:
        return ""

    # Format text dari history list
    text_block = ""
    for m in history:
        # Handle format legacy Gemini jika masih ada
        content = m.get('content', '')
        if not content and 'parts' in m:
            content = m['parts'][0]['text']

        role = m['role']
        text_block += f"{role}: {content}\n"

    prompt = f"""
Ringkas percakapan berikut menjadi memori jangka panjang yang padat.
Simpan fakta penting, preferensi user, emosi, dan konteks diskusi.
Jangan ulangi kalimat secara verbatim. Langsung berikan ringkasannya.

Percakapan:
{text_block}
"""

    try:
        # Perhatikan: Kita tidak pakai 'await' di sini karena client Groq Python
        # aslinya synchronous. Tapi karena ini dijalankan di background task (bot-main),
        # blocking sebentar tidak masalah, atau idealnya di-wrap executor.
        # Untuk simplifikasi, kita panggil langsung:

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Kamu adalah peringkas percakapan yang ahli."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_FAST,  # Pakai Llama 3 8B biar hemat & cepat
            temperature=0.5,
            max_tokens=500
        )

        return chat_completion.choices[0].message.content.strip()

    except Exception as e:
        print(f"[SUMMARIZER ERROR] {e}")
        return ""
