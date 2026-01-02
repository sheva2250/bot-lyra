from grok_client import grok_chat

async def summarize_history(history: list) -> str:
    if not history:
        return ""

    lines = []
    for m in history:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        lines.append(f"{role}: {content}")

    text = "\n".join(lines)

    messages = [
        {
            "role": "system",
            "content": (
                "Ringkas percakapan berikut menjadi memori jangka panjang. "
                "Simpan fakta penting, preferensi, emosi, dan konteks. "
                "Gunakan bullet points. Jangan mengulang kalimat verbatim."
            ),
        },
        {"role": "user", "content": text},
    ]

    return await grok_chat(messages, temperature=0.3, max_tokens=150)
