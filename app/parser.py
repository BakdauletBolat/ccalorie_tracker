import logging

from datetime import date

from google import genai
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ── Response schemas ────────────────────────────────────────


class ParsedFoodResponse(BaseModel):
    description: str
    short_description: str
    grams: float | None = None
    calories: float
    protein: float
    fat: float
    carbs: float
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
    "Извлеки данные о еде из сообщения пользователя.\n\n"
    "Сегодня: {today}.\n\n"
    "Правила:\n"
    "1. Если пользователь указал и калории, и КБЖУ — используй ЕГО числа без изменений.\n"
    "2. Если указаны только калории — используй их, КБЖУ оцени реалистично.\n"
    "3. Если чисел нет — оцени калории и КБЖУ по описанию еды и типичной порции.\n"
    "4. description — полное описание (например 'Хлеб с сыром').\n"
    "5. short_description — короткое название для списка.\n"
    "6. grams — вес в граммах, если указан, иначе null.\n"
    "7. Если указана дата (вчера, 5 мая) — верни date=YYYY-MM-DD, иначе null.\n\n"
    "Текст пользователя:\n"
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
        model="gemini-3.1-flash-lite",
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
        model="gemini-3.1-flash-lite",
        contents=OFF_TOPIC_PROMPT + text,
    )
    return response.text


async def parse_food_text(text: str) -> ParsedFoodResponse:
    logger.info("Парсинг текста через Gemini: %s", text)
    prompt = FOOD_PROMPT.format(today=date.today().isoformat())
    response = await _client.aio.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFoodResponse,
        ),
    )
    result = ParsedFoodResponse.model_validate_json(response.text)
    logger.info("Gemini результат: %s, date=%s", result.model_dump(exclude={"date"}), result.date)
    return result


async def parse_workout_text(text: str) -> ParsedWorkout:
    logger.info("Парсинг тренировки: %s", text)
    response = await _client.aio.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=WORKOUT_PROMPT.format(today=date.today().isoformat()) + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedWorkout,
        ),
    )
    result = ParsedWorkout.model_validate_json(response.text)
    logger.info("Тренировка результат: %s", result.model_dump())
    return result
