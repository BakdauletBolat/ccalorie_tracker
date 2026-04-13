import logging
from dataclasses import dataclass
import re

from datetime import date

from google import genai
from pydantic import BaseModel

from app.config import settings
from app.models import NutritionData

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)


@dataclass(frozen=True)
class ReferenceProduct:
    short_description: str
    aliases: tuple[str, ...]
    default_grams: float | None
    calories_per_100g: float
    protein_per_100g: float
    fat_per_100g: float
    carbs_per_100g: float


REFERENCE_PRODUCTS: tuple[ReferenceProduct, ...] = (
    ReferenceProduct("Хлеб", ("хлеб", "хлеб белый", "батон"), 45.0, 265.0, 9.0, 3.2, 49.0),
    ReferenceProduct("Сыр", ("сыр", "сыр российский", "сыр твердый", "твёрдый сыр"), 30.0, 360.0, 24.0, 30.0, 0.0),
    ReferenceProduct("Рис", ("рис", "рис вареный", "рис варёный"), 150.0, 116.0, 2.5, 0.3, 24.9),
    ReferenceProduct("Курица", ("курица", "куриная грудка", "грудка куриная", "куриное филе"), 150.0, 165.0, 23.0, 3.6, 0.0),
    ReferenceProduct("Банан", ("банан",), 120.0, 89.0, 1.1, 0.3, 22.8),
    ReferenceProduct("Яблоко", ("яблоко",), 180.0, 52.0, 0.3, 0.2, 14.0),
    ReferenceProduct("Яйцо", ("яйцо", "яйца"), 50.0, 143.0, 12.6, 9.5, 0.7),
    ReferenceProduct("Молоко", ("молоко",), 250.0, 52.0, 2.8, 2.5, 4.7),
    ReferenceProduct("Творог 0%", ("творог 0", "творог 0%", "обезжиренный творог"), 180.0, 71.0, 16.5, 0.0, 1.3),
    ReferenceProduct("Творог 5%", ("творог 5", "творог 5%"), 180.0, 121.0, 17.2, 5.0, 1.8),
    ReferenceProduct("Творог 9%", ("творог 9", "творог 9%"), 180.0, 159.0, 16.7, 9.0, 2.0),
    ReferenceProduct("Кофе", ("кофе", "американо", "эспрессо", "капучино"), 250.0, 2.0, 0.3, 0.0, 0.2),
    ReferenceProduct("Чай", ("чай",), 250.0, 1.0, 0.0, 0.0, 0.2),
    ReferenceProduct(
        "Протеин с водой",
        ("bombbar протеин", "bombbar protein", "протеин bombbar", "протеин с водой", "protein with water"),
        100.0,
        120.0,
        22.0,
        0.0,
        0.0,
    ),
    ReferenceProduct(
        "Exponenta",
        (
            "exponenta",
            "экспонента",
            "exponenta high protein",
            "exponenta высокобелковый кисломолочный напиток",
            "высокобелковый кисломолочный напиток exponenta",
        ),
        250.0,
        150.0,
        30.0,
        0.0,
        0.0,
    ),
    ReferenceProduct(
        "Гамбургер McDonald's",
        ("гамбургер макдональдс", "гамбургер mcdonalds", "mcdonalds hamburger", "mcdonalds hamburger", "гамбургер mc donalds"),
        100.0,
        257.0,
        12.0,
        10.0,
        30.0,
    ),
    ReferenceProduct(
        "Дабл чизбургер",
        ("дабл чизбургер", "double cheeseburger", "макдональдс дабл чизбургер", "mcdonalds double cheeseburger"),
        167.0,
        271.9,
        15.0,
        15.0,
        19.2,
    ),
)


# ── Response schemas ────────────────────────────────────────


class ParsedProductItem(BaseModel):
    description: str          # "Хлеб белый 45 г"
    short_description: str    # "Хлеб"
    grams: float | None = None
    calories: float
    protein: float
    fat: float
    carbs: float


class ParsedFoodResponse(BaseModel):
    items: list[ParsedProductItem]


class ParsedIntent(BaseModel):
    intent: str  # "food", "history", "workout", "other"
    date: str | None = None


class ParsedWorkout(BaseModel):
    description: str
    calories: float
    date: str  # YYYY-MM-DD


# ── Prompts ─────────────────────────────────────────────────


FOOD_PROMPT = (
    "Пользователь описал что он ел. Разбери КАЖДЫЙ продукт ОТДЕЛЬНО.\n\n"
    "Правила:\n"
    "1. Каждый продукт — отдельный элемент в списке items.\n"
    "2. Для каждого продукта верни:\n"
    "   - description: полное описание (например 'Хлеб белый 45 г')\n"
    "   - short_description: короткое название (например 'Хлеб')\n"
    "   - grams: вес в граммах (число) или null, если вес неважен/неуместен\n"
    "   - calories, protein, fat, carbs: КБЖУ\n\n"
    "3. Если пользователь указал вес (граммы) — рассчитай КБЖУ ТОЧНО НА ЭТОТ ВЕС.\n"
    "   Никогда не возвращай КБЖУ на 100 г, если в grams указано другое значение.\n"
    "   calories, protein, fat, carbs должны соответствовать именно указанной порции, а не справочным данным на 100 г.\n"
    "4. Если пользователь указал калории только для одного продукта — используй их только для этого продукта, "
    "а остальные продукты оценивай самостоятельно.\n"
    "5. Если пользователь указал калории — calories должны совпадать с указанным значением, "
    "остальные нутриенты оцени реалистично.\n"
    "6. Если ничего не указано — используй типичную порцию и оцени КБЖУ.\n"
    "7. Для штучных продуктов (яйцо, банан, яблоко) — считай за 1 штуку. "
    "Можно указать типичный вес, если он уместен.\n"
    "8. Для напитков (кофе, чай, сок) — считай стандартную чашку/стакан. "
    "Если вес в граммах неважен для отображения, верни grams=null.\n"
    "9. Не смешивай несколько продуктов в один элемент, даже если они написаны в одной фразе.\n"
    "10. short_description должен быть коротким и удобным для списка: "
    "например 'Хлеб', 'Сыр', 'Курица', 'Кофе'.\n\n"
    "ВАЖНО: обрабатывай каждый продукт независимо. Если у одного продукта указаны "
    "ккал или граммы, а у другого нет — это нормально, рассчитай каждый по своим данным.\n\n"
    "Текст пользователя:\n"
)

CONTEXT_FOOD_PROMPT = (
    "Пользователь ведёт список еды. Вот текущий список:\n"
    "{current}\n\n"
    "Пользователь написал: \"{text}\"\n\n"
    "Верни обновлённый полный список продуктов.\n"
    "Пользователь может добавлять, убирать или заменять продукты.\n\n"
    "Правила:\n"
    "1. Каждый продукт — отдельный элемент в списке items.\n"
    "2. Для каждого продукта верни: description, short_description, grams, "
    "calories, protein, fat, carbs.\n"
    "3. Если указан вес — рассчитай КБЖУ ТОЧНО НА ЭТОТ ВЕС.\n"
    "   Никогда не возвращай КБЖУ на 100 г, если в grams указано другое значение.\n"
    "   calories, protein, fat, carbs должны соответствовать именно указанной порции, а не справочным данным на 100 г.\n"
    "4. Если указаны калории только для части продуктов — применяй их только к этим продуктам.\n"
    "5. Если ничего не указано — используй типичную порцию.\n"
    "6. Если вес неважен или неуместен для отображения, верни grams=null.\n"
    "7. Обрабатывай каждый продукт независимо.\n"
    "8. Верни полный итоговый список после изменений пользователя, а не только новые продукты.\n"
)

INTENT_PROMPT = (
    "Определи намерение пользователя. Ответь одним из:\n"
    '- intent="history" — пользователь хочет посмотреть историю питания '
    "(например: 'что я ел вчера', 'покажи за 5 апреля'). "
    "Укажи date в формате YYYY-MM-DD.\n"
    '- intent="food" — пользователь описывает что он ел или пил.\n'
    '- intent="workout" — пользователь описывает тренировку или сколько калорий сжёг '
    "(например: 'сжёг 500 ккал', 'пробежал 5 км', 'тренировка 1 час'). "
    "Укажи date в формате YYYY-MM-DD если указана дата.\n"
    '- intent="other" — всё остальное, не связано с едой, историей и тренировками.\n\n'
    "Сегодня: {today}.\n"
    "Текст пользователя:\n"
)

OFF_TOPIC_PROMPT = (
    "Ты — КалорийБот, бот для учёта питания в Telegram. "
    "Пользователь написал что-то не по теме. "
    "Ответь одним предложением, максимум 10 слов. "
    "Напомни что ты умеешь записывать еду и показывать историю. "
    "Каждый раз отвечай по-разному.\n\n"
    "Сообщение пользователя:\n"
)

WORKOUT_PROMPT = (
    "Пользователь описал тренировку или сколько калорий сжёг. Извлеки:\n"
    "- description: краткое описание тренировки\n"
    "- calories: сколько калорий сожжено (ккал)\n"
    "- date: дата тренировки в формате YYYY-MM-DD. Если дата не указана, используй сегодняшнюю.\n\n"
    "Если калории не указаны, оцени приблизительно по типу активности.\n"
    "Сегодня: {today}.\n"
    "Текст пользователя:\n"
)


# ── Functions ───────────────────────────────────────────────


def _normalize_product_name(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^a-zа-я0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _find_reference_product(text: str) -> ReferenceProduct | None:
    haystack = _normalize_product_name(text)
    for product in REFERENCE_PRODUCTS:
        for alias in product.aliases:
            alias_normalized = _normalize_product_name(alias)
            if alias_normalized and alias_normalized in haystack:
                return product
    return None


def _format_reference_block(text: str) -> str:
    matched: list[ReferenceProduct] = []
    normalized_text = _normalize_product_name(text)
    for product in REFERENCE_PRODUCTS:
        if any(_normalize_product_name(alias) in normalized_text for alias in product.aliases):
            matched.append(product)

    if not matched:
        return ""

    lines = [
        "\nСправочные продукты для этого сообщения. Используй их как приоритетный источник:\n",
    ]
    for product in matched:
        default_grams = "null" if product.default_grams is None else f"{product.default_grams:.0f}"
        lines.append(
            f"- {product.short_description}: aliases={', '.join(product.aliases)}; "
            f"default_grams={default_grams}; "
            f"per_100g={product.calories_per_100g:.0f} ккал, {product.protein_per_100g:.1f} Б, "
            f"{product.fat_per_100g:.1f} Ж, {product.carbs_per_100g:.1f} У"
        )
    lines.append(
        "Если продукт найден в этом справочнике, используй его default_grams и per_100g как источник истины. "
        "Если пользователь указал свой вес, пересчитай строго от справочных per_100g на этот вес.\n"
    )
    return "\n".join(lines)


def _nutrition_from_reference(product: ReferenceProduct, grams: float) -> tuple[float, float, float, float]:
    ratio = grams / 100.0
    return (
        product.calories_per_100g * ratio,
        product.protein_per_100g * ratio,
        product.fat_per_100g * ratio,
        product.carbs_per_100g * ratio,
    )


def _normalize_item_with_reference(item: ParsedProductItem) -> ParsedProductItem:
    reference = _find_reference_product(f"{item.short_description} {item.description}")
    if not reference:
        return item

    grams = item.grams if item.grams is not None else reference.default_grams
    if grams is None:
        return item

    calories, protein, fat, carbs = _nutrition_from_reference(reference, grams)
    return ParsedProductItem(
        description=item.description,
        short_description=reference.short_description,
        grams=grams,
        calories=round(calories, 1),
        protein=round(protein, 1),
        fat=round(fat, 1),
        carbs=round(carbs, 1),
    )


def _normalize_items_with_reference(items: list[ParsedProductItem]) -> list[ParsedProductItem]:
    normalized = [_normalize_item_with_reference(item) for item in items]
    logger.info("Нормализовано по справочнику: %s", [i.model_dump() for i in normalized])
    return normalized


async def parse_intent(text: str) -> ParsedIntent:
    logger.info("Определение намерения: %s", text)
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=INTENT_PROMPT.format(today=date.today().isoformat()) + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedIntent,
        ),
    )
    result = ParsedIntent.model_validate_json(response.text)
    logger.info("Намерение: %s", result.model_dump())
    return result


async def generate_off_topic_reply(text: str) -> str:
    logger.info("Генерация off-topic ответа на: %s", text)
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=OFF_TOPIC_PROMPT + text,
    )
    return response.text


async def parse_food_text(text: str) -> list[ParsedProductItem]:
    logger.info("Парсинг текста через Gemini: %s", text)
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=FOOD_PROMPT + _format_reference_block(text) + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFoodResponse,
        ),
    )
    result = ParsedFoodResponse.model_validate_json(response.text)
    logger.info("Gemini результат: %s", [i.model_dump() for i in result.items])
    return _normalize_items_with_reference(result.items)


async def parse_workout_text(text: str) -> ParsedWorkout:
    logger.info("Парсинг тренировки: %s", text)
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=WORKOUT_PROMPT.format(today=date.today().isoformat()) + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedWorkout,
        ),
    )
    result = ParsedWorkout.model_validate_json(response.text)
    logger.info("Тренировка результат: %s", result.model_dump())
    return result


async def parse_food_with_context(text: str, current_items: list[str]) -> list[ParsedProductItem]:
    current = "\n".join(f"- {item}" for item in current_items) if current_items else "(пусто)"
    logger.info("Парсинг с контекстом: %s | текущий список: %s", text, current_items)
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=CONTEXT_FOOD_PROMPT.format(current=current, text=text) + _format_reference_block(text),
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFoodResponse,
        ),
    )
    result = ParsedFoodResponse.model_validate_json(response.text)
    logger.info("Gemini контекстный результат: %s", [i.model_dump() for i in result.items])
    return _normalize_items_with_reference(result.items)
