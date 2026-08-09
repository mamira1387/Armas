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
#
# نکته: تنها provider فعال برای این مدل روی هاگینگ‌فیس
# در حال حاضر Featherless AI است، پس حتماً باید ":featherless-ai"
# انتهای نام مدل باشد وگرنه خطای model_not_supported می‌گیری.
# =========================================================

MODEL = "DavidAU/Qwen3.6-27B-Fable-Fusion-711-Uncensored-Heretic-NM-DAU-MTP:featherless-ai"

HF_URL = "https://router.huggingface.co/v1/chat/completions"


# =========================================================
# Memory
# =========================================================

histories = {}


SYSTEM_PROMPT = """
تو «دلفین» هستی؛ یک هوش مصنوعی باهوش، تیز، بی‌حاشیه و کمی گستاخ.
شخصیتت پر از اعتماد به نفسه، شوخ‌طبعی داری، از کلیشه و پاسخ‌های
خشک و رباتیک بدت می‌آد. مثل یک دوست باهوش و رک حرف می‌زنی، نه مثل
یک دستیار رسمی و خنثی.

قوانین شخصیتی تو:
- مستقیم و بی‌مقدمه جواب بده؛ از پرحرفی و کلی‌گویی بیزاری.
- طنز و کنایه‌ی هوشمندانه بلدی، ولی هیچ‌وقت بی‌احترام یا توهین‌آمیز نیستی.
- وقتی کاربر سوال فنی یا جدی می‌پرسه، دقیق و کاربردی جواب می‌دی؛ فاز شوخی رو کنار می‌ذاری.
- از عبارات کلیشه‌ای مثل «به‌عنوان یک هوش مصنوعی نمی‌تونم...» استفاده نمی‌کنی؛
  اگر واقعاً کاری خارج از توانت یا نامعقول باشه، رک و کوتاه توضیح می‌دی چرا،
  و اگر می‌تونی جایگزین بهتری پیشنهاد می‌دی.
- هرگز به کاربر برای سوال پرسیدن یا خواستن کمک واکنش قضاوت‌گرانه نشون نمی‌دی.
- به زبان و لحن کاربر (رسمی/غیررسمی/فارسی/انگلیسی) خودتو تطبیق می‌دی.

هدف تو اینه که کاربر حس کنه داره با یه هوش مصنوعی باهوش و بامزه و
قابل‌اعتماد حرف می‌زنه، نه یه ربات خشک یا یه چیز خطرناک و غیرقابل کنترل.
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
            "temperature": 0.7,
            "max_tokens": 1200,
            "stream": False,
            # =================================================
            # مدل‌های خانواده Qwen3.5 به‌طور پیش‌فرض حالت
            # "thinking" دارند و بخش زیادی از توکن‌ها را صرف
            # فکر کردن داخلی (reasoning_content) می‌کنند.
            # با خاموش کردن آن، پاسخ مستقیم در content برمی‌گردد.
            # =================================================
            "chat_template_kwargs": {
                "enable_thinking": False
            },
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise Exception(
            f"HF {response.status_code}: {response.text[:2000]}"
        )

    data = response.json()

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise Exception(
            "Invalid Hugging Face response: "
            + str(data)[:2000]
        )

    content = message.get("content")

    # اگر با وجود خاموش بودن thinking، content هنوز خالی بود،
    # به‌عنوان فallback از reasoning_content استفاده می‌کنیم تا
    # کاربر پاسخ خالی نگیرد.
    if not content:
        content = message.get("reasoning_content")

    if not content:
        raise Exception(
            "Empty content from model: "
            + str(data)[:2000]
        )

    return content


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
# چون فایل api/webhook.py است، Vercel وقتی از سیستم روتینگ
# فایل‌محور (بدون vercel.json سفارشی) استفاده می‌کند، مسیر
# کامل درخواست یعنی "/api/webhook" را مستقیماً به همین اپ
# Flask پاس می‌دهد (نه فقط "/").
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
