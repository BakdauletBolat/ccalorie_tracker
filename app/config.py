from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    GEMINI_API_KEY: str
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "food_tracker"

    model_config = {"env_file": ".env"}


settings = Settings()  # type: ignore[call-arg]
