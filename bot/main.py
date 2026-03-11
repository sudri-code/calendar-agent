import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import ErrorEvent
from aiohttp import web

from bot.config import bot_settings
from bot.handlers import accounts
from bot.handlers import start, today, week, create, create_recurrence, reschedule, delete, find_slot, settings, contacts, text_input

logger = structlog.get_logger()


async def main():
    logging.basicConfig(level=getattr(logging, bot_settings.log_level))

    bot = Bot(
        token=bot_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = RedisStorage.from_url(bot_settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Global error handler for logging unhandled exceptions
    @dp.errors()
    async def error_handler(event: ErrorEvent):
        logger.error(
            "Unhandled exception in handler",
            exception=str(event.exception),
            update=str(event.update),
            exc_info=event.exception,
        )
        try:
            msg = event.update.message or (
                event.update.callback_query.message if event.update.callback_query else None
            )
            if msg:
                await msg.answer("Произошла ошибка. Попробуйте ещё раз или введите /cancel для сброса.")
        except Exception:
            pass

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
    dp.include_router(contacts.router)
    dp.include_router(text_input.router)   # must be last

    # Always remove any previously registered webhook first
    await bot.delete_webhook(drop_pending_updates=True)

    if bot_settings.bot_webhook_url:
        logger.info("Starting bot in webhook mode", url=bot_settings.bot_webhook_url)
        await bot.set_webhook(
            url=bot_settings.bot_webhook_url,
            secret_token=bot_settings.bot_webhook_secret,
            allowed_updates=dp.resolve_used_update_types(),
        )
        # Start aiohttp server to receive webhook updates from Telegram via nginx
        app = web.Application()
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=bot_settings.bot_webhook_secret,
        ).register(app, path="/webhook/telegram")
        setup_application(app, dp, bot=bot)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=8080)
        await site.start()
        logger.info("Webhook server listening", host="0.0.0.0", port=8080)
        await asyncio.Event().wait()
    else:
        logger.info("Starting bot in polling mode")
        await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
