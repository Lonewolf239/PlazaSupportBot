import asyncio
import logging

from bot_app import BOT_TOKEN, BotManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🤖 Бот техподдержки запущен...")

    bot_manager = BotManager(BOT_TOKEN, logger)
    await bot_manager.start_polling()


if __name__ == "__main__":
    asyncio.run(main())
