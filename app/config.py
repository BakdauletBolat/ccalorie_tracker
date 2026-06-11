from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    GEMINI_API_KEY: str
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "food_tracker"
    DEFAULT_TZ: str = "Asia/Almaty"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()  # type: ignore[call-arg]
