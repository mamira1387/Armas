import os
import requests
from flask import Flask, request, jsonify


# =========================================================
# Flask / Vercel
# =========================================================

app = Flask(__name__)


# =========================================================
# Environment Variables
# =========================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")

if not TELEGRAM_TOKEN:
    print("WARNING: TELEGRAM_TOKEN is not set", flush=True)

if not HF_TOKEN:
    print("WARNING: HF_TOKEN is not set", flush=True)


# =========================================================
# Hugging Face
# =========================================================

MODEL = "dphn/Dolphin3.0-R1-Mistral-24B:featherless-ai"

HF_URL = "https://router.huggingface.co/v1/chat/completions"


# =========================================================
# Memory
# =========================================================

histories = {}


SYSTEM_PROMPT = """
You are Dolphin, a conversational AI assistant.
You are good at natural conversation and roleplay.
Keep the conversation consistent and engaging.
"""


# =========================================================
# Dolphin / Hugging Face
# =========================================================

def ask_dolphin(messages):
    if not HF_TOKEN:
        raise Exception("HF_TOKEN is not configured")

    response = requests.post(
        HF_URL,
        headers={
            "Authorization": f"Bearer {HF_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 700,
            "stream": False,
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise Exception(
            f"HF {response.status_code}: {response.text[:2000]}"
        )

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise Exception(
            "Invalid Hugging Face response: "
            + str(data)[:2000]
        )


# =========================================================
# Telegram API
# =========================================================

def telegram_api(method, payload=None):
    if not TELEGRAM_TOKEN:
        raise Exception("TELEGRAM_TOKEN is not configured")

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{method}"
    )

    response = requests.post(
        url,
        json=payload or {},
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(
            f"Telegram HTTP {response.status_code}: "
            f"{response.text[:2000]}"
        )

    data = response.json()

    if not data.get("ok"):
        raise Exception(
            "Telegram API error: "
            + str(data)[:2000]
        )

    return data


def send_message(chat_id, text):
    # Telegram پیام‌های خیلی طولانی را قبول نمی‌کند.
    # برای اطمینان، متن را تکه‌تکه می‌کنیم.

    max_length = 4000

    if not text:
        text = "❌ پاسخ خالی دریافت شد."

    chunks = [
        text[i:i + max_length]
        for i in range(0, len(text), max_length)
    ]

    for chunk in chunks:
        telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
            }
        )


def send_typing(chat_id):
    try:
        telegram_api(
            "sendChatAction",
            {
                "chat_id": chat_id,
                "action": "typing",
            }
        )
    except Exception as e:
        print(
            "Typing action error:",
            repr(e),
            flush=True
        )


# =========================================================
# Telegram Update
# =========================================================

def process_update(data):
    message = data.get("message")

    if not message:
        return

    chat = message.get("chat", {})
    user = message.get("from", {})

    chat_id = chat.get("id")
    user_id = user.get("id")

    if chat_id is None or user_id is None:
        return

    text = message.get("text")

    if not text:
        return

    text = text.strip()

    # =====================================================
    # /start
    # =====================================================

    if text.startswith("/start"):
        send_message(
            chat_id,
            "🐬 سلام!\n\n"
            "Dolphin آماده است.\n"
            "پیامت رو بفرست."
        )
        return

    # =====================================================
    # /reset
    # =====================================================

    if text.startswith("/reset"):
        histories.pop(user_id, None)

        send_message(
            chat_id,
            "🧹 حافظه پاک شد."
        )
        return

    # =====================================================
    # Create History
    # =====================================================

    if user_id not in histories:
        histories[user_id] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

    histories[user_id].append(
        {
            "role": "user",
            "content": text,
        }
    )

    # =====================================================
    # Limit History
    # =====================================================

    if len(histories[user_id]) > 21:
        histories[user_id] = (
            [histories[user_id][0]]
            + histories[user_id][-20:]
        )

    # =====================================================
    # Ask Dolphin
    # =====================================================

    try:
        send_typing(chat_id)

        answer = ask_dolphin(
            histories[user_id]
        )

        if not answer:
            answer = "❌ Dolphin پاسخی برنگرداند."

        histories[user_id].append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        send_message(
            chat_id,
            answer
        )

    except Exception as e:
        print(
            "DOLPHIN ERROR:",
            repr(e),
            flush=True
        )

        send_message(
            chat_id,
            "❌ خطا در پردازش پیام:\n\n"
            + str(e)[:1500]
        )


# =========================================================
# Health Check
# =========================================================

@app.get("/")
def home():
    return jsonify(
        {
            "ok": True,
            "service": "Dolphin Telegram Bot",
            "status": "online",
        }
    )


# =========================================================
# Vercel Webhook
#
# مهم:
# چون فایل api/webhook.py است، Vercel وقتی از سیستم
# روتینگ فایل‌محور (بدون vercel.json سفارشی) استفاده کند،
# مسیر کامل درخواست یعنی "/api/webhook" را مستقیماً به
# همین اپ Flask پاس می‌دهد (نه فقط "/").
#
# به همین دلیل هر سه مسیر "/", "/webhook" و "/api/webhook"
# را روی یک تابع واحد ثبت می‌کنیم تا مهم نباشد Vercel چه
# مسیری را فوروارد می‌کند - همیشه پاسخ درست بگیریم.
# =========================================================

@app.post("/")
@app.post("/webhook")
@app.post("/api/webhook")
def webhook_handler():
    try:
        data = request.get_json(
            force=True,
            silent=False
        )

        print(
            "🔥 TELEGRAM UPDATE:",
            data,
            flush=True
        )

        process_update(data)

        return jsonify(
            {
                "ok": True
            }
        ), 200

    except Exception as e:
        print(
            "🔥 WEBHOOK ERROR:",
            repr(e),
            flush=True
        )

        return jsonify(
            {
                "ok": False,
                "error": str(e),
            }
        ), 500
