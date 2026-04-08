import logging

from app.bot import bot, dp
from app.database import connect, disconnect
from app.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Запуск приложения")
    connect()
    logger.info("MongoDB подключена")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        disconnect()
        logger.info("Приложение остановлено")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
