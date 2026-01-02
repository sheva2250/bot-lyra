import os
import requests
from dotenv import load_dotenv

load_dotenv()

XAI_API_KEY = os.getenv("XAI_API_KEY")
print(f"[DEBUG] API Key loaded: {XAI_API_KEY[:10]}..." if XAI_API_KEY else "[DEBUG] API Key is None!")

MODEL = os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning")

API_URL = "https://api.x.ai/v1/chat/completions"


def grok_chat(messages, temperature=0.5, max_tokens=120):
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    res = requests.post(API_URL, headers=headers, json=payload, timeout=30)

    # Add better error logging
    if res.status_code != 200:
        print(f"[API ERROR] Status: {res.status_code}")
        print(f"[API ERROR] Response: {res.text}")

    res.raise_for_status()

    data = res.json()
    return data["choices"][0]["message"]["content"]
