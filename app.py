import os
import requests
from flask import Flask, request

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_URL = "https://api.openai.com/v1/responses"

app = Flask(__name__)

# память пользователей
users = {}

SYSTEM_PROMPT = """
Ты менеджер проекта "Работа в Европе".
Ты собираешь данные: возраст, страна, гражданство.
После этого ты предлагаешь работу в Германии или Польше.
Пиши уверенно, коротко, по делу.
"""

def send(chat_id, text):
    requests.post(f"{TG_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

def ask_openai(messages):
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4.1-mini",
        "input": messages
    }

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=30)
    return r.json()["output"][0]["content"][0]["text"]

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    if chat_id not in users:
        users[chat_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        send(chat_id, "Привет! Напиши:\n1) возраст\n2) страну\n3) гражданство")
        return "ok"

    users[chat_id].append({"role": "user", "content": text})

    try:
        reply = ask_openai(users[chat_id])
    except:
        send(chat_id, "Ошибка AI. Попробуй ещё раз.")
        return "ok"

    users[chat_id].append({"role": "assistant", "content": reply})
    send(chat_id, reply)

    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
