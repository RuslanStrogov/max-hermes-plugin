# MAX Hermes Plugin

Платформенный плагин для [Hermes Agent](https://hermes-agent.nousresearch.com) — подключает мессенджер [MAX](https://max.ru) через Bot API.

## Возможности

- ✅ Приём и отправка текстовых сообщений
- ✅ Inline keyboard (кнопки с callback)
- ✅ Индикатор «Печатает...»
- ✅ Markdown-форматирование
- ✅ Белый список пользователей
- ✅ Webhook + Long Polling
- ✅ Отправка изображений (через upload API)

## Установка

### Из исходников

```bash
# Клонируйте репозиторий в папку плагинов Hermes
git clone https://github.com/RuslanStrogov/max-hermes-plugin.git \
  ~/.hermes/plugins/platforms/max

# Перезапустите Hermes Gateway
hermes gateway restart
```

### Через hermes plugins (если опубликован)

```bash
hermes plugins install max-platform
```

## Настройка

### 1. Создайте бота в MAX

1. Перейдите на [MAX для партнёров](https://business.max.ru)
2. Создайте чат-бота с разработкой
3. Получите токен бота

### 2. Настройте переменные окружения

```bash
# Добавьте в ~/.hermes/.env
MAX_BOT_TOKEN=your_bot_token_here
MAX_WEBHOOK_URL=https://your-domain.com/webhook
MAX_WEBHOOK_SECRET=optional-secret
```

Или через `config.yaml`:

```yaml
gateway:
  platforms:
    max:
      enabled: true
      extra:
        token: "your_bot_token"
        webhook_url: "https://your-domain.com/webhook"
        allowed_users: []
```

### 3. Настройте сервер

Nginx reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    location /webhook {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4. Запустите

```bash
hermes gateway restart
```

## Использование

После подключения бот будет автоматически:
- Принимать сообщения от пользователей MAX
- Передавать их агенту Hermes
- Отправлять ответы обратно в MAX

### Inline keyboard

Агент может отправлять сообщения с кнопками:

```python
# В системном промпте или через инструменты
buttons = [
    [{"text": "Да", "payload": "yes"}, {"text": "Нет", "payload": "no"}]
]
```

## Лицензия

MIT
