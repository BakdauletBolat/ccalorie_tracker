import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.bot.routers import all_routers
from app.clients import OpenFoodFactsClient
from app.config import settings
from app.llm import DeepSeekParser
from app.logger import setup_logging
from app.repositories import (
    FavoriteRepository,
    FoodRepository,
    PendingRepository,
    ProductCacheRepository,
    ProfileRepository,
    WorkoutRepository,
    connect,
    disconnect,
    ensure_indexes,
)
from app.services import (
    BarcodeService,
    FavoriteService,
    FoodService,
    ProfileService,
    StatsService,
    WorkoutService,
)

setup_logging()
logger = logging.getLogger(__name__)


def build_dispatcher(
    food_service: FoodService,
    workout_service: WorkoutService,
    profile_service: ProfileService,
    stats_service: StatsService,
    favorite_service: FavoriteService,
    barcode_service: BarcodeService,
    parser: DeepSeekParser,
) -> Dispatcher:
    dp = Dispatcher()
    dp["food_service"] = food_service
    dp["workout_service"] = workout_service
    dp["profile_service"] = profile_service
    dp["stats_service"] = stats_service
    dp["favorite_service"] = favorite_service
    dp["barcode_service"] = barcode_service
    dp["parser"] = parser
    for router in all_routers:
        dp.include_router(router)
    return dp


async def main() -> None:
    logger.info("Запуск приложения")
    db = connect()
    await ensure_indexes(db)
    logger.info("MongoDB подключена")

    foods = FoodRepository(db)
    workouts = WorkoutRepository(db)
    profiles = ProfileRepository(db)
    pending = PendingRepository(db)
    favorites = FavoriteRepository(db)
    product_cache = ProductCacheRepository(db)

    dp = build_dispatcher(
        food_service=FoodService(foods, pending),
        workout_service=WorkoutService(workouts),
        profile_service=ProfileService(profiles, foods),
        stats_service=StatsService(foods, workouts, profiles),
        favorite_service=FavoriteService(favorites, foods),
        barcode_service=BarcodeService(OpenFoodFactsClient(), product_cache),
        parser=DeepSeekParser(settings.DEEPSEEK_API_KEY),
    )

    bot = Bot(token=settings.TELEGRAM_TOKEN)
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск / профиль заново"),
        BotCommand(command="help", description="Что я умею"),
        BotCommand(command="history", description="Записи за сегодня"),
        BotCommand(command="week", description="Отчёт за неделю"),
        BotCommand(command="favorites", description="Избранные блюда"),
        BotCommand(command="clear", description="Очистить записи за сегодня"),
    ])
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        disconnect()
        logger.info("Приложение остановлено")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
