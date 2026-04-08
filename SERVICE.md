# КалорийБот — управление сервисом (macOS)

## Запуск

```bash
launchctl load ~/Library/LaunchAgents/com.faima.calorybot.plist
```

## Остановка

```bash
launchctl unload ~/Library/LaunchAgents/com.faima.calorybot.plist
```

## Перезапуск

```bash
launchctl kickstart -k gui/$(id -u)/com.faima.calorybot
```

## Статус

```bash
launchctl list | grep calorybot
```

Вывод: `PID status label` — если PID есть, сервис работает.

## Логи

```bash
# Логи приложения (ротация каждый день, хранит 30 дней)
tail -f logs/bot.log

# Логи launchd (stdout/stderr)
tail -f logs/launchd.log
tail -f logs/launchd-error.log
```

## MongoDB (Docker)

```bash
docker compose up -d     # запуск
docker compose down      # остановка
docker compose ps        # статус
```
