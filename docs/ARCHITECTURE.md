# 🏛 Архитектура

> Как устроен max-hermes-plugin изнутри.

```
┌─────────────────────────────────────┐
│          MAX Messenger              │
│  (max.ru: пользователи, чаты)       │
└──────────┬──────────────────────────┘
           │ HTTPS (Bot API)
           ▼
┌──────────────────┐     ┌──────────┐
│  max-hermes      │────▶│ Hermes   │
│  (bridge)        │◀────│ Agent    │
└──────────────────┘     └──────────┘

┌─────────────────────────────────────┐
│       max-hermes-plugin             │
│  ┌─────────────┐  ┌──────────────┐  │
│  │ Adapter     │  │ max_shared   │  │
│  │ (plugins/)  │  │ - client     │  │
│  │             │  │ - converter  │  │
│  │ • connect() │  │ - markdown   │  │
│  │ • listen()  │  │ - models     │  │
│  │ • send()    │  └──────────────┘  │
│  └─────────────┘                    │
└─────────────────────────────────────┘
```

## Компоненты

### Adapter (plugins/max_adapter.py)

Основной класс плагина. Регистрируется в Hermes Agent,
отвечает за lifecycle:
- `connect()` — регистрация вебхука и команд бота
- `listen()` — получение сообщений через webhook
- `send()` — отправка сообщений в MAX

### max_shared

Общая библиотека для работы с MAX Bot API:
- **max_client.py** — HTTP-клиент (send, upload, webhook setup)
- **converter.py** — конвертация форматов сообщений
- **markdown.py** — форматирование текста
- **models.py** — Pydantic-модели данных
- **constants.py** — константы (chat types, message types)