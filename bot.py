import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import router

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    
    bot = Bot(token=BOT_TOKEN)
    
    # Сбрасываем webhook и удаляем pending updates чтобы не было конфликта
    await bot.delete_webhook(drop_pending_updates=True)
    
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    print("🎬 Mmmovierate bot started!")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
