import os

# Заглушки до импорта app.config — тесты не требуют реальных токенов и .env
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
