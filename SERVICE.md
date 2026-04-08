# КалорийБот — управление сервисом

---

## Linux (systemd)

### Установка

```bash
sudo cp calorybot.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### Управление

```bash
sudo systemctl start calorybot      # запуск
sudo systemctl stop calorybot       # остановка
sudo systemctl restart calorybot    # перезапуск
sudo systemctl status calorybot     # статус
sudo systemctl enable calorybot     # автозапуск при загрузке
sudo systemctl disable calorybot    # отключить автозапуск
```

### Логи

```bash
journalctl -u calorybot -f          # логи в реальном времени
```

---

## macOS (launchd)

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
