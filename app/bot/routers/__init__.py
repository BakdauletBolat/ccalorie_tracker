from aiogram import Router

from app.bot.routers.favorites import router as favorites_router
from app.bot.routers.food import router as food_router
from app.bot.routers.help import router as help_router
from app.bot.routers.history import router as history_router
from app.bot.routers.onboarding import router as onboarding_router
from app.bot.routers.profile import router as profile_router
from app.bot.routers.week import router as week_router

# Порядок важен: food_router содержит catch-all хендлер и должен быть последним.
all_routers: list[Router] = [
    onboarding_router,
    help_router,
    profile_router,
    history_router,
    week_router,
    favorites_router,
    food_router,
]
