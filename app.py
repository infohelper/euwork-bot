import os
import time
import json
import threading
import requests
from flask import Flask, request

# ==== ENV ====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")  # можно не трогать

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
OPENAI_URL = "https://api.openai.com/v1/responses"

app = Flask(__name__)

# Память в RAM (для Free Render нормально)
user_state = {}          # chat_id -> {"stage": 0/1/2/3, "age":.., "country":.., "citizenship":..}
processed_updates = set()  # update_id to dedupe
processed_lock = threading.Lock()

SYSTEM_PROMPT = (
    "Ты автоответчик Telegram для проекта 'Работа в Европе'. "
    "Отвечай как живой менеджер: коротко, уверенно, дружелюбно. "
    "Сначала собери 3 пункта: возраст, страна где сейчас, гражданство. "
    "После этого задай 2-3 уточняющих вопроса (опыт/язык/какая страна интересует) и предложи следующий шаг."
)

def tg_send(chat_id: int, text: str):
    try:
        requests.post(
            f"{TG_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
    except Exception:
        pass

def ask_openai(user_text: str, context: dict) -> str:
    if not OPENAI_API_KEY:
        return "Есть тех.сбой на стороне сервиса. Напиши, пожалуйста: возраст, страна, гражданство — и я продолжу."

    profile = f"Профиль: возраст={context.get('age')}, страна={context.get('country')}, гражданство={context.get('citizenship')}."
    payload = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{profile}\nСообщение пользователя: {user_text}"}
        ],
        "temperature": 0.6
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=30)
    if r.status_code != 200:
        return "Есть тех.сбой на стороне сервиса. Напиши, пожалуйста: возраст, страна, гражданство — и я продолжу."

    data = r.json()

    # responses API: вытаскиваем весь текст из output
    out = []
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                out.append(c.get("text", ""))
    answer = "\n".join([x for x in out if x]).strip()

    return answer or "Ок, понял. Напиши, пожалуйста: возраст, страна, гражданство — и я продолжу."

def parse_profile(text: str):
    """
    Очень простой парсер: ожидаем что пользователь напишет примерно:
    '25 Таджикистан Таджикистан' или '25, Польша, Узбекистан'
    """
    t = text.replace(",", " ").replace(";", " ").replace("|", " ")
    parts = [p for p in t.split() if p.strip()]
    if len(parts) >= 3 and parts[0].isdigit():
        age = parts[0]
        country = parts[1]
        citizenship = parts[2]
        return age, country, citizenship
    return None

def handle_message(chat_id: int, text: str):
    st = user_state.get(chat_id, {"stage": 0})

    low = (text or "").strip().lower()

    if low in ("/start", "start"):
        user_state[chat_id] = {"stage": 0}
        tg_send(chat_id, "Привет! 👋 Чтобы подобрать работу, напиши в одном сообщении:\nВозраст + страна где ты сейчас + гражданство.\nНапример: 25 Польша Узбекистан")
        return

    # Если юзер сразу прислал 3 поля одной строкой
    parsed = parse_profile(text)
    if parsed:
        age, country, citizenship = parsed
        st = {"stage": 3, "age": age, "country": country, "citizenship": citizenship}
        user_state[chat_id] = st

        reply = ask_openai("Пользователь прислал данные. Продолжи диалог и задай уточняющие вопросы.", st)
        tg_send(chat_id, reply)
        return

    # Пошаговый сбор
    if st.get("stage", 0) == 0:
        user_state[chat_id] = {"stage": 1}
        tg_send(chat_id, "Привет! 👋 Скажи, пожалуйста, сколько тебе лет?")
        return

    if st.get("stage") == 1:
        user_state[chat_id] = {"stage": 2, "age": text.strip()}
        tg_send(chat_id, "Отлично. В какой стране ты сейчас находишься?")
        return

    if st.get("stage") == 2:
        st["stage"] = 3
        st["country"] = text.strip()
        user_state[chat_id] = st
        tg_send(chat_id, "Понял. Какое у тебя гражданство?")
        return

    if st.get("stage") == 3 and "citizenship" not in st:
        st["citizenship"] = text.strip()
        user_state[chat_id] = st
        reply = ask_openai("Данные собраны. Продолжи диалог.", st)
        tg_send(chat_id, reply)
        return

    # Уже собрали профиль -> отвечаем через OpenAI
    reply = ask_openai(text, st)
    tg_send(chat_id, reply)

def process_update(update: dict):
    try:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        if not text:
            return

        handle_message(chat_id, text)

    except Exception:
        # не падаем
        return

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

@app.route("/", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}
    upd_id = update.get("update_id")

    # DEDUPE: Telegram может прислать один апдейт несколько раз
    if upd_id is not None:
        with processed_lock:
            if upd_id in processed_updates:
                return "OK", 200
            processed_updates.add(upd_id)
            # чтобы set не рос бесконечно
            if len(processed_updates) > 5000:
                processed_updates.clear()

    # Главное: отвечаем Telegram быстро, а обработку делаем в фоне
    threading.Thread(target=process_update, args=(update,), daemon=True).start()
    return "OK", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
