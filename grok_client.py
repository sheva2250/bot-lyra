import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

XAI_API_KEY = os.getenv("XAI_API_KEY")
print(f"[DEBUG] API Key loaded: {XAI_API_KEY[:10]}..." if XAI_API_KEY else "[DEBUG] API Key is None!")

MODEL = os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning")

API_URL = "https://api.x.ai/v1/chat/completions"


async def grok_chat(messages, temperature=0.5, max_tokens=120):
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

    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(API_URL, headers=headers, json=payload) as res:
            if res.status != 200:
                text = await res.text()
                print(f"[API ERROR] Status: {res.status}")
                print(f"[API ERROR] Response: {text}")
                raise aiohttp.ClientError(f"API request failed with status {res.status}")
            
            data = await res.json()
            return data["choices"][0]["message"]["content"]
