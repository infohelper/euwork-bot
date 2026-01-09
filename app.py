from flask import Flask, request
import requests
import os

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# временное хранилище состояний пользователей
users = {}

def send(chat_id, text):
    requests.post(f"{TG_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

@app.route("/", methods=["POST"])
def telegram_webhook():
    data = request.get_json()

    if "message" not in data:
        return "ok", 200

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    # /start
    if text == "/start":
        users[chat_id] = {"step": "waiting_data"}
        send(chat_id, "Привет! 👋\nНапиши, пожалуйста:\nВозраст, страну и гражданство\n\nНапример:\n25, Tajikistan, Tajikistan")
        return "ok", 200

    # если ждём данные
    if chat_id in users and users[chat_id]["step"] == "waiting_data":
        users[chat_id]["data"] = text
        users[chat_id]["step"] = "done"

        send(chat_id, f"Спасибо! Я получил:\n{text}\n\nМенеджер скоро с вами свяжется.")
        return "ok", 200

    # всё остальное
    send(chat_id, "Напиши /start чтобы начать.")
    return "ok", 200


@app.route("/", methods=["GET"])
def health():
    return "OK", 200
