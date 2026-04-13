import logging

from datetime import date

from google import genai
from pydantic import BaseModel

from app.config import settings
from app.models import NutritionData

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)


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
        contents=FOOD_PROMPT + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFoodResponse,
        ),
    )
    result = ParsedFoodResponse.model_validate_json(response.text)
    logger.info("Gemini результат: %s", [i.model_dump() for i in result.items])
    return result.items


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
        contents=CONTEXT_FOOD_PROMPT.format(current=current, text=text),
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFoodResponse,
        ),
    )
    result = ParsedFoodResponse.model_validate_json(response.text)
    logger.info("Gemini контекстный результат: %s", [i.model_dump() for i in result.items])
    return result.items
