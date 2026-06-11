import logging
from datetime import date

from google import genai
from google.genai.errors import ClientError, ServerError

from app.llm import prompts
from app.llm.protocol import ParsedFoodList, ParsedMessage, ParserError

logger = logging.getLogger(__name__)

MODEL = "gemini-3.1-flash-lite"

Contents = str | list  # текст или [изображение, текст]


class GeminiParser:
    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    async def _generate(self, contents: Contents, schema: type | None = None) -> str:
        config = None
        if schema is not None:
            config = genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            )
        try:
            response = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=contents,
                config=config,
            )
        except (ServerError, ClientError) as e:
            logger.warning("Gemini ошибка: %s", e)
            raise ParserError(str(e)) from e
        return response.text

    async def parse_message(self, text: str, today: date) -> ParsedMessage:
        logger.info("Разбор сообщения: %s", text)
        raw = await self._generate(
            prompts.MESSAGE_PROMPT.format(today=today.isoformat()) + text,
            schema=ParsedMessage,
        )
        result = ParsedMessage.model_validate_json(raw)
        logger.info(
            "Разбор: intent=%s, products=%d, workout=%s, date=%s",
            result.intent, len(result.products),
            result.workout.model_dump() if result.workout else None, result.date,
        )
        return result

    async def parse_food(self, text: str, today: date) -> ParsedFoodList:
        logger.info("Парсинг еды: %s", text)
        raw = await self._generate(
            prompts.FOOD_PROMPT.format(today=today.isoformat()) + text,
            schema=ParsedFoodList,
        )
        result = ParsedFoodList.model_validate_json(raw)
        logger.info("Еда: products=%d, date=%s", len(result.products), result.date)
        return result

    async def parse_food_photo(
        self, image: bytes, caption: str | None, today: date,
    ) -> ParsedFoodList:
        logger.info("Парсинг фото еды (%d байт), подпись: %s", len(image), caption)
        prompt = prompts.PHOTO_PROMPT.format(today=today.isoformat())
        if caption:
            prompt += prompts.PHOTO_CAPTION_PROMPT + caption
        raw = await self._generate(
            [
                genai.types.Part.from_bytes(data=image, mime_type="image/jpeg"),
                prompt,
            ],
            schema=ParsedFoodList,
        )
        result = ParsedFoodList.model_validate_json(raw)
        logger.info("Фото: products=%d, date=%s", len(result.products), result.date)
        return result

    async def off_topic_reply(self, text: str) -> str:
        logger.info("Генерация off-topic ответа на: %s", text)
        return await self._generate(prompts.OFF_TOPIC_PROMPT + text)
