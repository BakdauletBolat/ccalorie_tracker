import logging

from datetime import date

from google import genai
from pydantic import BaseModel

from app.config import settings
from app.models import NutritionData

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)

PROMPT = (
    "Пользователь описал что он ел. Извлеки из текста:\n"
    "- description: краткое описание еды\n"
    "- calories: калории (ккал)\n"
    "- protein: белки (г)\n"
    "- fat: жиры (г)\n"
    "- carbs: углеводы (г)\n\n"
    "Если значение не указано, оцени приблизительно.\n"
    "Текст пользователя:\n"
)


class ParsedIntent(BaseModel):
    intent: str  # "food", "history", "other"
    date: str | None = None


INTENT_PROMPT = (
    "Определи намерение пользователя. Ответь одним из:\n"
    '- intent="history" — пользователь хочет посмотреть историю питания '
    "(например: 'что я ел вчера', 'покажи за 5 апреля'). "
    "Укажи date в формате YYYY-MM-DD.\n"
    '- intent="food" — пользователь описывает что он ел или пил.\n'
    '- intent="other" — всё остальное, не связано с едой и историей.\n\n'
    f"Сегодня: {date.today().isoformat()}.\n"
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


class ParsedFood(NutritionData):
    description: str


async def parse_intent(text: str) -> ParsedIntent:
    logger.info("Определение намерения: %s", text)
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=INTENT_PROMPT + text,
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


async def parse_food_text(text: str) -> ParsedFood:
    logger.info("Парсинг текста через Gemini: %s", text)
    response = await _client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=PROMPT + text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedFood,
        ),
    )
    result = ParsedFood.model_validate_json(response.text)
    logger.info("Gemini результат: %s", result.model_dump())
    return result
