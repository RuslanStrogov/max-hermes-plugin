# 📖 API Reference

> Поддерживаемые методы MAX Bot API и их использование в max-hermes-plugin.

## Базовый URL

Все запросы к MAX Bot API: `https://api-im.max.ru/`

## Методы

### sendMessage

Отправка текстового сообщения.

```python
POST /message/send
Content-Type: application/json
Authorization: <token>

{
    "chat_id": "123456789",
    "text": "Привет!",
    "parse_mode": "MARKDOWN"
}
```

### sendImage

Отправка изображения (через upload API).

```python
# 1. Загрузить файл
POST /uploads?type=image
Content-Type: multipart/form-data
# → { "data": { "token": "..." } }

# 2. Отправить сообщение с изображением
POST /message/send
{
    "chat_id": "123456789",
    "text": "Смотри:",
    "inline_keyboard_markup": { ... },
    "attachments": [{
        "type": "image",
        "payload": { "token": "..." }
    }]
}
```

### Ответ от сервера

```json
{
    "message": {
        "body": {
            "mid": "mid.xxx"
        }
    }
}
```

### Webhook

Получение входящих сообщений через POST на настроенный URL.

```json
POST /webhook
{
    "message": {
        "body": {
            "text": "/start",
            "from": { "user_id": "123" },
            "chat": { "chat_id": "456" }
        }
    }
}
```

## Обработка команд

| Команда | Описание |
|---------|----------|
| `/start` | Начать диалог с ботом |
| `/help` | Получить справку |
| `/about` | Информация о боте |

Команды обрабатываются на стороне плагина,
без вызова Hermes AI.

Подробнее: [max-openclaw — MAX Channel Plugin](https://github.com/RuslanStrogov/max-openclaw)