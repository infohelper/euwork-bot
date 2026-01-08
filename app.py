import os
import requests
from flask import Flask, request

# --- ENV (НЕ ПИШИ КЛЮЧИ В КОД!) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing env var: TELEGRAM_BOT_TOKEN")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing env var: OPENAI_API_KEY")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
OPENAI_URL = "https://api.openai.com/v1/responses"

app = Flask(__name__)

SYSTEM_PROMPT = """
Ты автоответчик Telegram для проекта "Работа в Европе".
Отвечай как живой менеджер: коротко, уверенно, дружелюбно, по делу.
Твоя цель — собрать заявку и перевести человека в диалог/запись.

Сначала всегда уточни 3 вещи:
1) Возраст
2) Страна где сейчас
3) Гражданство

Если человек уже дал эти данные — задай 2–3 уточняющих вопроса:
- Какая работа интересует (склад/завод/строя/гостиницы/другое)
- Есть ли опыт и какие документы
- Когда готов выехать/выйти на работу

В конце каждого ответа добавляй короткий призыв: "Напиши: возраст, страна, гражданство."
Язык ответа: русский (если пользователь пишет по-польски — отвечай по-польски).
"""

def tg_send(chat_id: int, text: str):
    requests.post(
        f"{TG_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=20
    )

def ask_openai(user_text: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_text.strip()}
        ],
        "max_output_tokens": 250
    }

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=45)
    r.raise_for_status()
    data = r.json()

    # Responses API возвращает output[]; вытаскиваем текст безопасно
    text_parts = []
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                text_parts.append(c.get("text", ""))

    answer = "\n".join([t for t in text_parts if t]).strip()
    return answer if answer else "Привет! Напиши, пожалуйста: возраст, страна, гражданство."

@app.route("/", methods=["GET"])
def healthcheck():
    return "OK", 200

@app.route("/", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return "ok", 200

    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = msg.get("text", "")

    if not chat_id:
        return "ok", 200

    try:
        reply = ask_openai(text)
    except Exception:
        reply = "Есть тех.сбой на стороне сервиса. Напиши, пожалуйста: возраст, страна, гражданство — я сразу продолжу."

    tg_send(chat_id, reply)
    return "ok", 200

# Для локального запуска (на Render обычно стартует gunicorn)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
