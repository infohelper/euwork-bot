import os
import re
import requests
from flask import Flask, request

# -------------------------
# ENV (Render Environment Variables)
# -------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY env var")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
OPENAI_URL = "https://api.openai.com/v1/responses"

app = Flask(__name__)

# Простая память (в RAM). После перезапуска Render память обнуляется — это нормально для старта.
user_state = {}  # chat_id -> {"age":..., "country":..., "citizenship":..., "ready": bool}


# -------------------------
# Helpers
# -------------------------
def tg_send(chat_id: int, text: str):
    requests.post(
        f"{TG_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=20,
    )


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_profile(text: str):
    """
    Очень простой парсер: пытается достать возраст/страну/гражданство из одной строки.
    Примеры:
      "25 таджикистан таджикистан"
      "Возраст 25, страна Польша, гражданство Узбекистан"
    """
    t = normalize_text(text).lower()

    # возраст
    age = None
    m = re.search(r"\b(\d{2})\b", t)
    if m:
        try:
            age_val = int(m.group(1))
            if 16 <= age_val <= 65:
                age = age_val
        except:
            pass

    # страна/гражданство (берём слова после возраста или по ключевым словам)
    country = None
    citizenship = None

    # Если есть "страна" / "гражданство"
    m_country = re.search(r"страна[:\s\-]*([a-zа-яё\- ]{2,30})", t, re.IGNORECASE)
    if m_country:
        country = normalize_text(m_country.group(1)).split(" ")[0].capitalize()

    m_cit = re.search(r"гражд[:\s\-]*([a-zа-яё\- ]{2,30})", t, re.IGNORECASE)
    if m_cit:
        citizenship = normalize_text(m_cit.group(1)).split(" ")[0].capitalize()

    # Если нет ключевых слов — пробуем формат "25 страна гражданство"
    if age is not None and (country is None or citizenship is None):
        parts = normalize_text(text).split()
        # найдём позицию возраста
        idx = None
        for i, p in enumerate(parts):
            if p.isdigit() and int(p) == age:
                idx = i
                break
        if idx is not None:
            after = parts[idx + 1 :]
            if len(after) >= 1 and country is None:
                country = after[0].capitalize()
            if len(after) >= 2 and citizenship is None:
                citizenship = after[1].capitalize()

    return age, country, citizenship


def openai_reply(chat_id: int, user_message: str, profile: dict):
    """
    Запрос в OpenAI Responses API.
    """
    system = f"""
Ты — менеджер по трудоустройству в Германии (проект "Работа в Европе").
Твоя задача — быстро провести первичный скрининг и вести человека к оформлению.

Тон: коротко, уверенно, дружелюбно. Без воды.
Язык: русский.

Если данных ещё нет (возраст/страна/гражданство) — сначала собери их.
Когда собрал — уточни:
1) есть ли загранпаспорт
2) есть ли опыт работы и кем
3) есть ли права категории B
4) когда готов выехать

После этого предложи 2–3 направления вакансий в Германии (склад/завод/стройка/логистика) и следующий шаг.

Профиль кандидата (может быть пустым):
Возраст: {profile.get("age")}
Страна где сейчас: {profile.get("country")}
Гражданство: {profile.get("citizenship")}
"""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.4,
        "max_output_tokens": 400,
    }

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=40)
    r.raise_for_status()
    data = r.json()

    # В responses API текст обычно лежит в output->content
    # Делаем безопасный извлекатель
    out_text = ""
    try:
        for item in data.get("output", []):
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    out_text += c.get("text", "")
    except:
        pass

    out_text = normalize_text(out_text)
    if not out_text:
        out_text = "Принял. Напиши, пожалуйста: возраст, страна где сейчас, гражданство."

    return out_text


# -------------------------
# Routes
# -------------------------
@app.get("/")
def health():
    return "OK", 200


@app.post("/")
def telegram_webhook():
    data = request.get_json(force=True, silent=True) or {}

    if "message" not in data:
        return "ok", 200

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = normalize_text(msg.get("text", ""))

    # init state
    if chat_id not in user_state:
        user_state[chat_id] = {"age": None, "country": None, "citizenship": None, "ready": False}

    st = user_state[chat_id]

    # /start
    if text.lower().startswith("/start"):
        st["age"], st["country"], st["citizenship"] = None, None, None
        st["ready"] = False
        tg_send(
            chat_id,
            "Привет! Я менеджер по вакансиям в Германии 🇩🇪\n"
            "Напиши одним сообщением:\n"
            "✅ возраст\n✅ страна где сейчас\n✅ гражданство\n"
            "Пример: 25 Таджикистан Таджикистан",
        )
        return "ok", 200

    # Пытаемся распарсить профиль
    age, country, citizenship = extract_profile(text)
    if age is not None:
        st["age"] = age
    if country:
        st["country"] = country
    if citizenship:
        st["citizenship"] = citizenship

    # Если ещё не собрали всё — просим недостающее
    missing = []
    if not st["age"]:
        missing.append("возраст")
    if not st["country"]:
        missing.append("страна где сейчас")
    if not st["citizenship"]:
        missing.append("гражданство")

    if missing:
        tg_send(chat_id, "Нужно ещё: " + ", ".join(missing) + ".\nПример: 25 Таджикистан Таджикистан")
        return "ok", 200

    # Всё собрали → AI-ответ
    reply = openai_reply(chat_id, text, st)
    tg_send(chat_id, reply)
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
