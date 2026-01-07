import os, time, random
from flask import Flask, request
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

TG = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
OPENAI_URL = "https://api.openai.com/v1/responses"

application = Flask(__name__)
app = application


SYSTEM = """
Ты автоответчик Telegram для проекта "Работа в Европе".
Отвечай как живой менеджер.
Сначала собери:
1) Возраст
2) Страна где сейчас
3) Гражданство
Пиши коротко, уверенно, дружелюбно.
"""

def tg_send(chat_id, text):
    requests.post(f"{TG}/sendMessage", json={"chat_id": chat_id, "text": text})

def ask_openai(text):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text}
        ]
    }
    r = requests.post(OPENAI_URL, headers=headers, json=payload)
    data = r.json()

    out = []
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                out.append(c.get("text", ""))
    return ("\n".join(out)) or "Напиши возраст и гражданство 🙂"

@app.post("/webhook")
def webhook():
    msg = request.json.get("message")
    if not msg:
        return "ok"

    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    time.sleep(random.randint(2,5))

    reply = ask_openai(text)
    tg_send(chat_id, reply)
    return "ok"

@app.get("/")
def home():
    return "OK"
