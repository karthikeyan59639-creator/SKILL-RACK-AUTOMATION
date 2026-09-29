import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY", "")
key_loaded = bool(api_key and api_key.strip())
print(f"[TEST GEMINI] Key loaded: {key_loaded}")

model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
headers = {
    "Content-Type": "application/json",
    "x-goog-api-key": api_key
}
payload = {
    "contents": [{"parts": [{"text": "Write a 1-line Python program that prints hello"}]}],
    "generationConfig": {
        "temperature": 0.1,
        "maxOutputTokens": 1024
    }
}

print(f"[TEST GEMINI] Sending test request to model '{model}'...")
try:
    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    print(f"[TEST GEMINI] HTTP Status Code: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        reply = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for p in parts:
                if "text" in p:
                    reply += p["text"]
        print(f"[TEST GEMINI] Extracted Reply:\n{reply}")
    else:
        print(f"[TEST GEMINI] Response Body: {resp.text}")
except Exception as e:
    print(f"[TEST GEMINI] Request Exception: {e}")

