"""
Скрипт рассылки обновления бота всем пользователям.
Запуск: uv run python send_update.py
"""

import asyncio
import logging

from aiogram import Bot
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPDATE_TEXT = """
<b>🔄 Обновление CALorie Tracker 0.0.5</b>

Бот стал умнее, честнее и теперь понимает контекст.

<b>Что нового:</b>

1. <b>Твои калории — закон</b>
Написал «250 ккал хлеб»? Будет ровно 250. Бот больше не спорит и не подставляет свои цифры.

2. <b>«Хлеб с сыром» = одно блюдо</b>
Раньше бот разбивал на «хлеб» и «сыр» отдельно, как будто ты ешь их в разных комнатах. Исправлено.

3. <b>Запись на другую дату</b>
Забыл записать вчерашний ужин? Напиши «вчера ел плов» — бот сохранит с правильной датой 📅

Приятного аппетита!
""".strip()


async def main() -> None:
    bot = Bot(token=settings.TELEGRAM_TOKEN)
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]

    cursor = db.food_entries.aggregate([
        {"$group": {"_id": "$user_id"}},
    ])
    user_ids: list[int] = [doc["_id"] async for doc in cursor]
    logger.info("Найдено %d пользователей", len(user_ids))

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, UPDATE_TEXT, parse_mode="HTML")
            sent += 1
            logger.info("Отправлено user=%s", uid)
        except Exception as e:
            failed += 1
            logger.warning("Не удалось отправить user=%s: %s", uid, e)
        await asyncio.sleep(0.05)  # rate limit

    logger.info("Готово: отправлено %d, ошибок %d", sent, failed)

    client.close()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
