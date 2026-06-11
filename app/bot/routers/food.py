import logging
from datetime import date

from aiogram import F, Router, types

from app.bot import texts
from app.bot.keyboards import barcode_grams_keyboard, confirmed_keyboard, pending_keyboard
from app.bot.routers.history import show_day
from app.llm.protocol import FoodParser, ParsedFoodList, ParserError
from app.models import ProductInfo, ProductItem, UserProfile
from app.services import BarcodeService, FoodService, ProfileService, StatsService, WorkoutService
from app.services import time_service
from app.services.food_service import products_from_parsed

logger = logging.getLogger(__name__)

router = Router(name="food")


@router.callback_query(F.data.startswith("pdel:"))
async def cb_pending_delete(
    callback: types.CallbackQuery, food_service: FoodService, profile_service: ProfileService,
) -> None:
    user_id = callback.from_user.id
    index = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    removed, meal = await food_service.remove_pending_item(user_id, index)
    if removed is None:
        await callback.answer("Не найдено")
        return

    if meal is None:
        await callback.message.edit_text("Список очищен.")  # type: ignore[union-attr]
        await callback.answer()
        return

    profile = await profile_service.get(user_id)
    today = time_service.today(profile.timezone if profile else None)
    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.pending_text(meal.items, meal.entry_date, today),
        reply_markup=pending_keyboard(meal.items),
        parse_mode="HTML",
    )
    await callback.answer(f"Убрано: {removed.description}")


@router.callback_query(F.data == "confirm")
async def cb_confirm(
    callback: types.CallbackQuery, food_service: FoodService, profile_service: ProfileService,
) -> None:
    user_id = callback.from_user.id
    profile = await profile_service.get(user_id)
    tz = profile.timezone if profile else None

    meal = await food_service.get_pending(user_id)
    confirmed = await food_service.confirm_pending(user_id, tz)
    if confirmed is None:
        await callback.answer("Нет записей для сохранения")
        return
    entry_id, entry = confirmed

    today = time_service.today(tz)
    entry_date = meal.entry_date if meal else None
    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.confirmed_text(entry, entry_date, today),
        reply_markup=confirmed_keyboard(entry_id),
        parse_mode="HTML",
    )
    await callback.answer("Записано!")


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: types.CallbackQuery, food_service: FoodService) -> None:
    await food_service.cancel_pending(callback.from_user.id)
    await callback.message.edit_text("🚫 Отменено.")  # type: ignore[union-attr]
    await callback.answer()


async def _show_added_pending(
    message: types.Message,
    user_id: int,
    products: list[ProductItem],
    entry_date: date | None,
    food_service: FoodService,
    today: date,
) -> None:
    """Добавляет продукты в pending (или создаёт его) и показывает список."""
    if await food_service.get_pending(user_id) is not None:
        meal = await food_service.append_pending(user_id, products, entry_date)
    else:
        meal = await food_service.start_pending(user_id, products, entry_date)

    await message.answer(
        texts.pending_text(meal.items, meal.entry_date, today),
        reply_markup=pending_keyboard(meal.items),
        parse_mode="HTML",
    )


async def _add_to_pending(
    message: types.Message,
    user_id: int,
    parsed: ParsedFoodList,
    food_service: FoodService,
    today: date,
    empty_reply: str,
) -> None:
    if not parsed.products:
        await message.answer(empty_reply)
        return
    products = products_from_parsed(parsed.products)
    entry_date = date.fromisoformat(parsed.date) if parsed.date else None
    await _show_added_pending(message, user_id, products, entry_date, food_service, today)


async def _handle_barcode_product(
    message: types.Message,
    user_id: int,
    info: ProductInfo,
    food_service: FoodService,
    parser: FoodParser,
    today: date,
) -> None:
    """Продукт найден по штрих-коду: вес из карточки → в pending, иначе выбор граммов.

    Если в карточке OFF нет КБЖУ — оцениваем по названию через LLM.
    """
    if info.calories_100g is None:
        await message.answer(
            f"📦 Нашёл продукт: <b>{info.name}</b>, но КБЖУ в базе не заполнены. "
            "Оцениваю по названию...",
            parse_mode="HTML",
        )
        query = info.name
        if info.package_grams:
            query += f", {info.package_grams:.0f} г"
        try:
            parsed = await parser.parse_food(query, today)
        except ParserError:
            await message.answer(texts.SERVICE_OVERLOADED)
            return
        await _add_to_pending(
            message, user_id, parsed, food_service, today,
            empty_reply="Не получилось оценить продукт 😕 Опиши его текстом.",
        )
        return

    if info.package_grams is not None:
        item = BarcodeService.to_product_item(info, info.package_grams)
        await _show_added_pending(message, user_id, [item], None, food_service, today)
        return

    await message.answer(
        texts.barcode_grams_text(info),
        reply_markup=barcode_grams_keyboard(info.barcode),
        parse_mode="HTML",
    )


async def _prepare(message: types.Message, profile_service: ProfileService) -> tuple[int, UserProfile | None, date]:
    user_id = message.from_user.id  # type: ignore[union-attr]
    # Автоснимок профиля при первом сообщении за день
    profile = await profile_service.ensure_today_snapshot(user_id)
    today = time_service.today(profile.timezone if profile else None)
    return user_id, profile, today


@router.callback_query(F.data.startswith("bcg:"))
async def cb_barcode_grams(
    callback: types.CallbackQuery,
    food_service: FoodService,
    profile_service: ProfileService,
    barcode_service: BarcodeService,
) -> None:
    # format: bcg:<barcode>:<grams>
    _, barcode, grams_str = callback.data.split(":", 2)  # type: ignore[union-attr]
    grams = float(grams_str)
    user_id = callback.from_user.id

    info = await barcode_service.lookup(barcode)
    if info is None or info.calories_100g is None:
        await callback.answer("Продукт не найден")
        return

    profile = await profile_service.ensure_today_snapshot(user_id)
    tz = profile.timezone if profile else None
    today = time_service.today(tz)

    item = BarcodeService.to_product_item(info, grams)
    _, entry = await food_service.record_items(user_id, [item], None, tz)
    logger.info("user=%s записал по штрих-коду %s: %s", user_id, barcode, item.description)

    await callback.message.edit_text(  # type: ignore[union-attr]
        texts.confirmed_text(entry, None, today),
        parse_mode="HTML",
    )
    await callback.answer("Записано!")


@router.message(F.photo)
async def handle_photo(
    message: types.Message,
    food_service: FoodService,
    profile_service: ProfileService,
    barcode_service: BarcodeService,
    parser: FoodParser,
) -> None:
    user_id, _, today = await _prepare(message, profile_service)
    logger.info("user=%s отправил фото, подпись: %s", user_id, message.caption)

    photo = message.photo[-1]  # type: ignore[index]  # самое большое разрешение
    file = await message.bot.get_file(photo.file_id)  # type: ignore[union-attr]
    buffer = await message.bot.download_file(file.file_path)  # type: ignore[union-attr, arg-type]
    image = buffer.read()  # type: ignore[union-attr]

    # Сначала штрих-код — это быстро, точно и без LLM
    barcode = barcode_service.decode(image)
    if barcode:
        info = await barcode_service.lookup(barcode)
        if info:
            await _handle_barcode_product(message, user_id, info, food_service, parser, today)
            return
        await message.answer(
            f"Штрих-код <code>{barcode}</code> не найден в базе 😕 "
            "Пробую распознать как фото еды...",
            parse_mode="HTML",
        )

    await message.answer("Распознаю фото... 📷")

    try:
        parsed = await parser.parse_food_photo(image, message.caption, today)
    except ParserError:
        await message.answer(texts.SERVICE_OVERLOADED)
        return

    await _add_to_pending(
        message, user_id, parsed, food_service, today,
        empty_reply="Не смог распознать еду на фото 📷 Попробуй другой ракурс или опиши текстом.",
    )


@router.message()
async def handle_food(
    message: types.Message,
    food_service: FoodService,
    workout_service: WorkoutService,
    profile_service: ProfileService,
    stats_service: StatsService,
    barcode_service: BarcodeService,
    parser: FoodParser,
) -> None:
    if not message.text:
        return

    user_id, profile, today = await _prepare(message, profile_service)
    tz = profile.timezone if profile else None
    logger.info("user=%s отправил текст: %s", user_id, message.text)

    # Штрих-код цифрами — ищем в базе без LLM
    digits = message.text.strip()
    if digits.isdigit() and 8 <= len(digits) <= 14:
        info = await barcode_service.lookup(digits)
        if info:
            await _handle_barcode_product(message, user_id, info, food_service, parser, today)
        else:
            await message.answer(f"Штрих-код {digits} не найден в базе 😕")
        return

    # Если есть pending — новый текст трактуем только как продукты для добавления.
    if await food_service.get_pending(user_id) is not None:
        await message.answer("Обрабатываю...")
        try:
            parsed = await parser.parse_food(message.text, today)
        except ParserError:
            await message.answer(texts.SERVICE_OVERLOADED)
            return
        await _add_to_pending(
            message, user_id, parsed, food_service, today,
            empty_reply="Не понял, что добавить. Опиши продукт, например: «сыр 30г».",
        )
        return

    await message.answer("Обрабатываю...")
    try:
        result = await parser.parse_message(message.text, today)
    except ParserError:
        await message.answer(texts.SERVICE_OVERLOADED)
        return

    if result.intent == "history":
        day = date.fromisoformat(result.date) if result.date else today
        await show_day(message, user_id, stats_service, profile_service, day)
        return

    if result.intent == "workout":
        if result.workout is None:
            await message.answer("Не понял тренировку. Напиши, например: «пробежал 5 км».")
            return
        workout_day = date.fromisoformat(result.date) if result.date else today
        entry = await workout_service.add(
            user_id=user_id,
            description=result.workout.description,
            calories=result.workout.calories,
            day=workout_day,
            tz_name=tz,
        )
        await message.answer(
            f"🏋️ <b>Тренировка записана!</b>\n\n"
            f"💪 {entry.description}\n"
            f"🔥 Сожжено: <b>{entry.calories:.0f}</b> ккал",
            parse_mode="HTML",
        )
        return

    if result.intent == "other":
        try:
            reply = await parser.off_topic_reply(message.text)
            await message.answer(reply)
        except ParserError:
            await message.answer("Я умею записывать еду и показывать историю питания 🍽")
        return

    # intent == "food"
    parsed = ParsedFoodList(products=result.products, date=result.date)
    await _add_to_pending(
        message, user_id, parsed, food_service, today,
        empty_reply="Не понял, что ты съел 🤔 Попробуй описать иначе, например: «гречка 150г и курица».",
    )
