import base64
import json
import logging
from datetime import date

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel

from app.llm import prompts
from app.llm.protocol import ParsedFoodList, ParsedMessage, ParserError

logger = logging.getLogger(__name__)

MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
MAX_TOKENS = 4096


def _schema_instructions(schema: type[BaseModel]) -> str:
    """DeepSeek json_object режим: схему передаём в промпте + слово «json»."""
    return (
        "\n\nВерни ответ строго как JSON-объект (json), без markdown и пояснений, "
        "по этой схеме:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


class DeepSeekParser:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=BASE_URL)

    async def _generate(
        self,
        prompt: str,
        *,
        image: bytes | None = None,
        schema: type[BaseModel] | None = None,
    ) -> str:
        if schema is not None:
            prompt += _schema_instructions(schema)

        if image is not None:
            data_uri = "data:image/jpeg;base64," + base64.b64encode(image).decode()
            content: str | list = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]
        else:
            content = prompt

        kwargs: dict = {"max_tokens": MAX_TOKENS}
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": content}],
                **kwargs,
            )
        except APIError as e:
            logger.warning("DeepSeek ошибка: %s", e)
            raise ParserError(str(e)) from e

        text = response.choices[0].message.content
        if not text:
            logger.warning("DeepSeek вернул пустой ответ")
            raise ParserError("Пустой ответ от модели")
        return text

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
        raw = await self._generate(prompt, image=image, schema=ParsedFoodList)
        result = ParsedFoodList.model_validate_json(raw)
        logger.info("Фото: products=%d, date=%s", len(result.products), result.date)
        return result

    async def off_topic_reply(self, text: str) -> str:
        logger.info("Генерация off-topic ответа на: %s", text)
        return await self._generate(prompts.OFF_TOPIC_PROMPT + text)
