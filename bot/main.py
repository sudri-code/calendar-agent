import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web

from bot.config import bot_settings
from bot.handlers import accounts
from bot.handlers import start, today, week, create, create_recurrence, reschedule, delete, find_slot, settings

logger = structlog.get_logger()


async def main():
    logging.basicConfig(level=getattr(logging, bot_settings.log_level))

    bot = Bot(
        token=bot_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = RedisStorage.from_url(bot_settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Register routers
    dp.include_router(start.router)
    dp.include_router(today.router)
    dp.include_router(week.router)
    dp.include_router(create.router)
    dp.include_router(create_recurrence.router)
    dp.include_router(reschedule.router)
    dp.include_router(delete.router)
    dp.include_router(find_slot.router)
    dp.include_router(accounts.router)
    dp.include_router(settings.router)

    # Start bot
    if bot_settings.bot_webhook_url:
        logger.info("Starting bot in webhook mode", url=bot_settings.bot_webhook_url)
        await bot.set_webhook(
            url=f"{bot_settings.bot_webhook_url}",
            secret_token=bot_settings.bot_webhook_secret,
        )
        # Webhook server would be set up here
        await dp.start_polling(bot, skip_updates=True)
    else:
        logger.info("Starting bot in polling mode")
        await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
