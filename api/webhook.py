import os
import asyncio
import requests

from flask import Flask, request, jsonify

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
HF_TOKEN = os.environ["HF_TOKEN"]

MODEL = "dphn/Dolphin3.0-R1-Mistral-24B:featherless-ai"
HF_URL = "https://router.huggingface.co/v1/chat/completions"

histories = {}

SYSTEM_PROMPT = """
You are Dolphin, a conversational AI assistant.
You are good at natural conversation and roleplay.
Keep the conversation consistent and engaging.
"""


def ask_dolphin(messages):
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
            f"HF {response.status_code}: {response.text}"
        )

    data = response.json()

    return data["choices"][0]["message"]["content"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐬 سلام!\n\n"
        "Dolphin آماده است.\n"
        "پیامت رو بفرست."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    histories.pop(user_id, None)

    await update.message.reply_text(
        "🧹 حافظه پاک شد."
    )


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in histories:
        histories[user_id] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

    histories[user_id].append({
        "role": "user",
        "content": text
    })

    if len(histories[user_id]) > 21:
        histories[user_id] = (
            [histories[user_id][0]]
            + histories[user_id][-20:]
        )

    try:
        await update.message.chat.send_action("typing")

        answer = ask_dolphin(histories[user_id])

        histories[user_id].append({
            "role": "assistant",
            "content": answer
        })

        await update.message.reply_text(answer)

    except Exception as e:
        print("DOLPHIN ERROR:", repr(e), flush=True)

        await update.message.reply_text(
            "❌ خطا:\n" + str(e)[:1000]
        )


telegram_app = (
    Application.builder()
    .token(TELEGRAM_TOKEN)
    .build()
)

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    CommandHandler("reset", reset)
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        chat
    )
)


@app.get("/")
def home():
    return "🐬 Dolphin Telegram Bot is online!"


@app.post("/webhook")
def webhook():
    try:
        data = request.get_json(force=True)

        print(
            "🔥 TELEGRAM UPDATE:",
            data,
            flush=True
        )

        update = Update.de_json(
            data,
            telegram_app.bot
        )

        # اجرای async بدون async view در Flask
        asyncio.run(
            telegram_app.process_update(update)
        )

        return jsonify({
            "ok": True
        })

    except Exception as e:
        print(
            "🔥 WEBHOOK ERROR:",
            repr(e),
            flush=True
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
