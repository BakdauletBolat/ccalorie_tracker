import logging

from datetime import date

from google import genai
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ── Справочник продуктов (передаётся в промпт как контекст для Gemini) ──

REFERENCE_PRODUCTS: dict[str, dict] = {
    "Хлеб": {"default_grams": 45, "cal": 265, "p": 9.0, "f": 3.2, "c": 49.0},
    "Сыр": {"default_grams": 30, "cal": 360, "p": 24.0, "f": 30.0, "c": 0.0},
    "Рис варёный": {"default_grams": 150, "cal": 116, "p": 2.5, "f": 0.3, "c": 24.9},
    "Куриная грудка": {"default_grams": 150, "cal": 165, "p": 23.0, "f": 3.6, "c": 0.0},
    "Банан": {"default_grams": 120, "cal": 89, "p": 1.1, "f": 0.3, "c": 22.8},
    "Яблоко": {"default_grams": 180, "cal": 52, "p": 0.3, "f": 0.2, "c": 14.0},
    "Яйцо": {"default_grams": 50, "cal": 143, "p": 12.6, "f": 9.5, "c": 0.7},
    "Молоко": {"default_grams": 250, "cal": 52, "p": 2.8, "f": 2.5, "c": 4.7},
    "Творог 0%": {"default_grams": 180, "cal": 71, "p": 16.5, "f": 0.0, "c": 1.3},
    "Творог 5%": {"default_grams": 180, "cal": 121, "p": 17.2, "f": 5.0, "c": 1.8},
    "Творог 9%": {"default_grams": 180, "cal": 159, "p": 16.7, "f": 9.0, "c": 2.0},
    "Кофе": {"default_grams": 250, "cal": 2, "p": 0.3, "f": 0.0, "c": 0.2},
    "Чай": {"default_grams": 250, "cal": 1, "p": 0.0, "f": 0.0, "c": 0.2},
    "Протеин с водой (bombbar)": {"default_grams": 300, "cal": 40, "p": 7.3, "f": 0.0, "c": 0.0},
    "Exponenta": {"default_grams": 250, "cal": 60, "p": 12.0, "f": 0.0, "c": 0.0},
    "Гамбургер McDonald's": {"default_grams": 102, "cal": 250, "p": 11.9, "f": 10.0, "c": 30.0},
    "Дабл чизбургер McDonald's": {"default_grams": 167, "cal": 272, "p": 15.0, "f": 15.0, "c": 19.2},
}


def _build_reference_block() -> str:
    lines = ["Справочник продуктов (КБЖУ на 100 г, default_grams — типичная порция):"]
    for name, d in REFERENCE_PRODUCTS.items():
        lines.append(
            f"- {name}: {d['cal']} ккал, {d['p']}Б {d['f']}Ж {d['c']}У на 100г, "
            f"порция {d['default_grams']}г"
        )
    lines.append(
        "\nИспользуй этот справочник для оценки КБЖУ, если продукт совпадает. "
        "Пересчитывай на указанный вес. "
        "Но если пользователь ЯВНО указал свои калории — используй ЕГО число, не справочное.\n"
    )
    return "\n".join(lines)


REFERENCE_BLOCK = _build_reference_block()


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
    date: str | None = None  # YYYY-MM-DD, None = сегодня


class ParsedIntent(BaseModel):
    intent: str  # "food", "history", "workout", "other"
    date: str | None = None


class ParsedWorkout(BaseModel):
    description: str
    calories: float
    date: str  # YYYY-MM-DD


# ── Prompts ─────────────────────────────────────────────────


FOOD_PROMPT = (
    "Пользователь описал что он ел. Разбери на отдельные блюда/приёмы пищи.\n\n"
    "Сегодня: {today}.\n\n"
    "Правила:\n"
    "1. Каждое БЛЮДО — отдельный элемент в списке items.\n"
    "   - Если продукты составляют одно блюдо (например 'хлеб с сыром', 'рис с курицей', "
    "'макароны с соусом'), верни их КАК ОДНО блюдо с суммарным КБЖУ.\n"
    "   - Разделяй на отдельные элементы только действительно разные блюда "
    "(например 'суп и салат' — два элемента).\n"
    "2. Для каждого блюда верни:\n"
    "   - description: полное описание (например 'Хлеб с сыром')\n"
    "   - short_description: короткое название (например 'Хлеб с сыром')\n"
    "   - grams: вес в граммах (число) или null, если вес неважен/неуместен\n"
    "   - calories, protein, fat, carbs: КБЖУ\n\n"
    "3. САМОЕ ВАЖНОЕ: если пользователь указал калории (ккал) — calories ДОЛЖНЫ ТОЧНО совпадать "
    "с указанным числом. Никогда не меняй калории, которые пользователь указал сам. "
    "Остальные нутриенты (protein, fat, carbs) оцени реалистично.\n"
    "4. Если пользователь указал вес (граммы) — рассчитай КБЖУ на этот вес.\n"
    "5. Если пользователь указал калории только для одного продукта — используй их только для этого продукта, "
    "а остальные оценивай самостоятельно.\n"
    "6. Если ничего не указано — используй типичную порцию и оцени КБЖУ.\n"
    "7. Для штучных продуктов (яйцо, банан, яблоко) — считай за 1 штуку.\n"
    "8. Для напитков (кофе, чай, сок) — считай стандартную чашку/стакан. "
    "Если вес в граммах неважен, верни grams=null.\n"
    "9. short_description должен быть коротким и удобным для списка.\n"
    "10. Если пользователь указал дату (вчера, позавчера, 5 апреля и т.д.) — "
    "верни date в формате YYYY-MM-DD. Если дата не указана — верни date=null.\n\n"
    "Текст пользователя:\n"
)

CONTEXT_FOOD_PROMPT = (
    "Пользователь ведёт список еды. Вот текущий список:\n"
    "{current}\n\n"
    "Пользователь написал: \"{text}\"\n\n"
    "Сегодня: {today}.\n\n"
    "Верни обновлённый полный список блюд.\n"
    "Пользователь может добавлять, убирать или заменять блюда.\n\n"
    "Правила:\n"
    "1. Каждое БЛЮДО — отдельный элемент в списке items.\n"
    "   Если продукты составляют одно блюдо (например 'хлеб с сыром'), "
    "верни их как одно блюдо с суммарным КБЖУ.\n"
    "2. Для каждого блюда верни: description, short_description, grams, "
    "calories, protein, fat, carbs.\n"
    "3. САМОЕ ВАЖНОЕ: если пользователь указал калории (ккал) — calories ДОЛЖНЫ ТОЧНО совпадать "
    "с указанным числом. Никогда не меняй калории пользователя.\n"
    "4. Если указан вес — рассчитай КБЖУ на этот вес.\n"
    "5. Если ничего не указано — используй типичную порцию.\n"
    "6. Если вес неважен, верни grams=null.\n"
    "7. Верни полный итоговый список после изменений пользователя.\n"
    "8. Если пользователь указал дату (вчера, позавчера и т.д.) — "
    "верни date в формате YYYY-MM-DD. Если дата не указана — верни date=null.\n"
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


async def parse_food_text(text: str) -> ParsedFoodResponse:
    logger.info("Парсинг текста через Gemini: %s", text)
    prompt = FOOD_PROMPT.format(today=date.today().isoformat())
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=REFERENCE_BLOCK + "\n" + prompt + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFoodResponse,
        ),
    )
    result = ParsedFoodResponse.model_validate_json(response.text)
    logger.info("Gemini результат: %s, date=%s", [i.model_dump() for i in result.items], result.date)
    return result


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


async def parse_food_with_context(text: str, current_items: list[str]) -> ParsedFoodResponse:
    current = "\n".join(f"- {item}" for item in current_items) if current_items else "(пусто)"
    logger.info("Парсинг с контекстом: %s | текущий список: %s", text, current_items)
    prompt = CONTEXT_FOOD_PROMPT.format(current=current, text=text, today=date.today().isoformat())
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=REFERENCE_BLOCK + "\n" + prompt,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFoodResponse,
        ),
    )
    result = ParsedFoodResponse.model_validate_json(response.text)
    logger.info("Gemini контекстный результат: %s, date=%s", [i.model_dump() for i in result.items], result.date)
    return result
