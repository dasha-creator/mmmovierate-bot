import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import BOT_TOKEN
from database import init_db
from handlers import router

logging.basicConfig(level=logging.INFO)

WEBHOOK_PATH = "/webhook"
WEBAPP_PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # будет задан в Railway


async def on_startup(bot: Bot):
    await init_db()
    if WEBHOOK_URL:
        await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}", drop_pending_updates=True)
        print(f"🎬 Webhook set: {WEBHOOK_URL}{WEBHOOK_PATH}")
    else:
        print("⚠️  WEBHOOK_URL not set, falling back to polling")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()


def run_polling():
    """Fallback если нет WEBHOOK_URL"""
    async def main():
        await init_db()
        bot = Bot(token=BOT_TOKEN)
        await bot.delete_webhook(drop_pending_updates=True)
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(router)
        print("🎬 Bot started (polling)")
        await dp.start_polling(bot)
    asyncio.run(main())


def run_webhook():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    print(f"🎬 Bot started (webhook) on port {WEBAPP_PORT}")
    web.run_app(app, host="0.0.0.0", port=WEBAPP_PORT)


if __name__ == "__main__":
    if WEBHOOK_URL:
        run_webhook()
    else:
        run_polling()
