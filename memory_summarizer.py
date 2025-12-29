import google.generativeai as genai
# Import API_KEY_POOL untuk otentikasi
from config import MODEL_NAME, API_KEY_POOL

async def summarize_history(history: list) -> str:
    """
    Summarize conversation history.
    Handles Gemini format: [{"role": "user", "parts": [{"text": "..."}]}]
    """
    if not history:
        return ""
    
    # SETUP API KEY (Ambil key pertama dari pool)
    if API_KEY_POOL:
        genai.configure(api_key=API_KEY_POOL[0])
    
    # Format text dari history object
    text_lines = []
    for m in history:
        role = m.get('role', 'unknown')
        content = ""
        
        # Handle format Gemini (parts) vs format simple (content)
        if 'parts' in m and isinstance(m['parts'], list):
            content = m['parts'][0]['text']
        elif 'content' in m:
            content = m['content']
            
        text_lines.append(f"{role}: {content}")

    text = "\n".join(text_lines)

    prompt = f"""
Ringkas percakapan berikut menjadi memori jangka panjang.
Simpan fakta penting, preferensi, emosi, dan konteks.
Jangan ulangi kalimat secara verbatim.

Percakapan:
{text}
"""

    try:
        model = genai.GenerativeModel(model_name=MODEL_NAME)
        # Gunakan await untuk async
        resp = await model.generate_content_async(prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"[SUMMARIZER ERROR] {e}")
        return ""
