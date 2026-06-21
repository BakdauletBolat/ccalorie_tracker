import os

# Заглушки до импорта app.config — тесты не требуют реальных токенов и .env
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
