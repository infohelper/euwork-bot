import os
import requests
from flask import Flask, request

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_URL = "https://api.openai.com/v1/responses"

app = Flask(__name__)

SYSTEM_PROMPT = """
Ты Telegram-менеджер проекта "Работа в Европе".
Твоя задача — вести диалог, как живой человек.

Сначала обязательно собери:
1) возраст
2) страна где сейчас
3) гражданство

После этого:
задай вопросы про опыт, желаемую страну и тип работы.

Пиши коротко, уверенно, дружелюбно.
Никаких технических фраз.
"""

def send_message(chat_id, text):
    requests.post(f"{TG_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

def ask_openai(text):
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ]
    }

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=30)
    data = r.json()

    return data["output"][0]["content"][0]["text"]

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        try:
            reply = ask_openai(text)
        except Exception:
            reply = "Есть техническая ошибка, попробуй ещё раз через минуту."

        send_message(chat_id, reply)

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
