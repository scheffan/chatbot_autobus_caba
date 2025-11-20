import os
import logging
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
CHAT_ENDPOINT = f"{API_BASE}/api/chat"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("colectivos-bot")

if not BOT_TOKEN:
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN en .env")

async def call_backend(user_id: str, text: str) -> str:
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(CHAT_ENDPOINT, json={"user_id": str(user_id), "text": text})
        r.raise_for_status()
        data = r.json()
        return (data.get("text") or "").strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "¡Hola! Soy tu asistente de colectivos 🚍\n\n"
            "Podés decirme:\n"
            "• *ir de* Corrientes 800 *a* Rivadavia 6300\n"
            "• *guardar casa:* <dirección>\n"
            "• *guardar trabajo:* <dirección>\n"
            "• *ver próximas 3* / *ver frecuencias*\n\n"
            "Después de ver opciones, también entiendo *la 1*, *la más rápida*, *la del 132*, etc."
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = (update.message.text or "").strip()
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    try:
        reply = await call_backend(user_id=str(chat_id), text=user_text)
        if not reply:
            reply = "No recibí respuesta. Probá de nuevo."
        await context.bot.send_message(chat_id=chat_id, text=reply, parse_mode=ParseMode.MARKDOWN)
    except httpx.HTTPError:
        log.exception("HTTP error")
        await context.bot.send_message(chat_id=chat_id, text="No pude hablar con el servidor. ¿Está el backend en :8000?")
    except Exception:
        log.exception("Unexpected error")
        await context.bot.send_message(chat_id=chat_id, text="Ups, me trabé. Probá de nuevo.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    log.info("Bot iniciado. Escuchando mensajes…")
    app.run_polling()

if __name__ == "__main__":
    main()
