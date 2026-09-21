<div align="center">

  <img src="banner.png" alt="MAX Hermes Plugin Banner" width="100%"/>

  <br/>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/aiohttp-3.9+-2C5BB4?logo=aiohttp&logoColor=white" alt="aiohttp"/>
  <img src="https://img.shields.io/badge/Pydantic-2.0+-E92063?logo=pydantic&logoColor=white" alt="Pydantic"/>
  <img src="https://img.shields.io/badge/MAX-Bot%20API-6366F1?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iIzYzNjZmMSI+PHBhdGggZD0iTTEyIDJMMTggOEwxOCAyMkw2IDIyTDYgOEwxMiAyWiIvPjwvc3ZnPg==&logoColor=white" alt="MAX"/>
  <img src="https://img.shields.io/badge/Hermes-Agent-8B5CF6" alt="Hermes"/>
  <img src="https://img.shields.io/badge/Hermes%20Gateway-Plugin-8B5CF6" alt="Gateway"/>
  <img src="https://img.shields.io/badge/Nginx-009639?logo=nginx&logoColor=white" alt="Nginx"/>
  <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions"/>
  <img src="https://img.shields.io/badge/Let's%20Encrypt-003A70?logo=letsencrypt&logoColor=white" alt="Let's Encrypt"/>
  <img src="https://img.shields.io/badge/License-MIT-22C55E" alt="MIT"/>

  <h3>Нативный платформенный плагин для <a href="https://hermes-agent.nousresearch.com">Hermes Agent</a></h3>
  <p>Подключает мессенджер <a href="https://max.ru">MAX</a> через Bot API — полная интеграция с AI-агентом</p>
  <p><strong>Версия плагина:</strong> 2.0.0</p>

  <table>
    <tr>
      <td width="50%" align="center">
        <h4>🇷🇺 Российская разработка</h4>
        <p>Сделано в Кремёнках · Open source · MIT</p>
      </td>
      <td width="50%" align="center">
        <h4>🎨 Designed by <a href="https://br-design.ru/">BR-DESIGN</a></h4>
        <p>Дизайн, брендинг, визуальный стиль</p>
      </td>
    </tr>
  </table>

</div>

---

## 📋 Содержание

- [Архитектура](#-архитектура)
- [Возможности](#-возможности)
- [Bot Commands Menu](#-bot-commands-menu)
- [Требования](#-требования)
- [Установка](#-установка)
- [Настройка](#-настройка)
- [Переменные окружения](#-переменные-окружения)
- [Запуск](#-запуск)
- [Использование](#-использование)
- [Структура проекта](#-структура-проекта)
- [Сравнение с Telegram Bot API](#-сравнение-с-telegram-bot-api)
- [Тестирование](#-тестирование)
- [Устранение неполадок](#-устранение-неполадок)
- [Релизы и CI/CD](#-релизы-и-cicd)
- [Лицензия](#-лицензия)

---

## 🏗️ Архитектура

```
┌──────────┐   webhook    ┌─────────────────┐   gateway    ┌──────────────┐
│          │ ──────────►  │                 │ ──────────►  │              │
│ MAX Bot  │              │ MAX Plugin      │              │ Hermes Agent │
│ API      │ ◄──────────  │ (Hermes         │ ◄──────────  │ (Gateway)    │
│          │  send_msg    │  Gateway)       │  response    │              │
└──────────┘              └─────────────────┘              └──────────────┘
                                │
                          ┌─────┴─────┐
                          │ max_shared │
                          │ (библиотека)│
                          └───────────┘
```

1. Пользователь пишет боту в MAX (или выбирает команду из меню)
2. MAX API отправляет webhook на плагин
3. Плагин обрабатывает команды `/start`, `/help`, `/about` напрямую
4. Остальные сообщения — плагин показывает индикатор «Печатает...»
5. Плагин передаёт сообщение в Hermes Gateway (нативная интеграция — не через CLI)
6. Ответ Hermes отправляется обратно в MAX через Bot API

> **Нужен standalone-мост (не плагин)?** Используйте [MAX Hermes Bridge](https://github.com/RuslanStrogov/max-hermes) — Python-демон с Docker, systemd и CI/CD.

## ✨ Возможности

### Полная интеграция

| Фича | Статус |
|------|--------|
| Приём сообщений от MAX через webhook | ✅ |
| Отправка ответов в MAX | ✅ |
| Индикатор «Печатает...» пока агент думает | ✅ |
| **Bot Commands Menu (/start, /help, /about)** | ✅ |
| **Регистрация команд при старте (PATCH /me/commands)** | ✅ |
| **Обработка /команд без вызова Hermes** | ✅ |
| Inline keyboard (кнопки в сообщении) | ✅ |
| Callback от кнопок | ✅ |
| Поддержка нескольких пользователей | ✅ |
| Белый список пользователей (ALLOWED_USERS) | ✅ |
| Markdown-форматирование ответов | ✅ |
| Health check endpoint (/health) | ✅ |
| Дедупликация сообщений (in-memory cache) | ✅ |
| HMAC-верификация webhook (опционально) | ✅ |

### Типы сообщений и вложения

| Фича | Статус |
|------|--------|
| Текстовые сообщения | ✅ |
| Изображения (через upload API) | ✅ |
| Файлы (через upload API) | ✅ |
| Callback events (нажатие кнопок) | ✅ |
| Групповые чаты (group/channel) | ✅ |
| Маршрутизация: chat_id для групп, user_id для DM | ✅ |

### Инфраструктура

| Фича | Статус |
|------|--------|
| Конфигурация через config.yaml | ✅ |
| Конфигурация через переменные окружения | ✅ |
| Long Polling (GET /updates) | ✅ |
| Webhook subscriptions (POST/GET/DELETE) | ✅ |
| Cron/уведомления (home_channel) | ✅ |
| Логирование (через Hermes Gateway) | ✅ |
| Совместимость с Hermes send_message | ✅ |

### Общая библиотека (max_shared)

| Компонент | Назначение |
|-----------|------------|
| `MAXClient` | HTTP-клиент для MAX Bot API (aiohttp) |
| `MessageConverter` | Конвертация сообщений MAX ↔ Hermes |
| `Markdown` | Определение и обработка Markdown-разметки |
| `Models` | Pydantic-модели для MAX API |
| `Constants` | Константы (таймауты, лимиты, URL по умолчанию) |

## 🎛️ Bot Commands Menu

При подключении плагин автоматически регистрирует команды бота через `PATCH /me/commands` на `platform-api2.max.ru`.

**Зарегистрированные команды:**

| Команда | Описание |
|---------|----------|
| `/start` | Начать диалог с ботом |
| `/help` | Помощь и информация о боте |
| `/about` | О боте и его возможностях |

Команды обрабатываются **напрямую в плагине**, без вызова Hermes AI:

```python
# adapter.py — добавлено в connect()
await self._client.set_commands([
    {"name": "start", "description": "Начать диалог с ботом"},
    {"name": "help", "description": "Помощь и информация о боте"},
    {"name": "about", "description": "О боте и его возможностях"},
])
```

Регистронезависимо: `/Start`, `/HELP`, `/About` — все сработают.

### Пример использования

1. Пользователь открывает диалог с ботом в MAX
2. Нажимает кнопку вызова команд (рядом с полем ввода)
3. Выбирает `/help`
4. Плагин сразу отвечает справкой — без ожидания Hermes

## 📋 Требования

- Python 3.11+
- Hermes Agent (сборка с поддержкой Gateway-плагинов)
- Сервер с публичным IP (или tunnel) для приёма webhook
- SSL-сертификат (Let's Encrypt или самоподписанный)
- Бот на платформе MAX (требуется юрлицо, ИП или самозанятый)

## 📦 Установка

### 1. Клонирование репозитория

```bash
# Клонируйте репозиторий в папку плагинов Hermes
git clone https://github.com/RuslanStrogov/max-hermes-plugin.git \
  ~/.hermes/plugins/platforms/max

cd ~/.hermes/plugins/platforms/max
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка конфигурации

Добавьте в `~/.hermes/config.yaml`:

```yaml
gateway:
  platforms:
    max:
      enabled: true
      extra:
        token: "your_bot_token_here"
        webhook_url: "https://your-domain.com/webhook"
        webhook_secret: "optional-secret-for-hmac"
        api_base_url: "https://platform-api.max.ru"
        allowed_users: []           # empty = allow all
        home_channel: ""            # chat ID for cron delivery
```

Или через переменные окружения в `~/.hermes/.env`:

```bash
MAX_BOT_TOKEN=your_bot_token_here
MAX_WEBHOOK_URL=https://your-domain.com/webhook
MAX_WEBHOOK_SECRET=your_secret
```

### 4. Перезапуск Gateway

```bash
hermes gateway restart
```

## ⚙️ Настройка

### Создание бота в MAX

> ⚠️ **Важно:** Создание ботов на платформе MAX доступно **только юридическим лицам, ИП и самозанятым** (резидентам РФ). Физическим лицам создание ботов **недоступно**.

| Тип профиля | Кол-во ботов |
|---|---|
| Организация / ИП | Несколько (не ограничено платформой) |
| Самозанятый | Ограничено |

**Пошаговая инструкция:**

1. Перейдите на [портал MAX для партнёров](https://business.max.ru)
2. **Создайте и верифицируйте профиль** организации, ИП или самозанятого
3. В панели управления нажмите **«Добавить бота»**
4. Заполните данные бота (карточка):
   - **Название** — от 1 до 59 символов
   - **Никнейм** — генерируется автоматически (должен заканчиваться на `_bot`)
   - Сайт организации, логотип и описание
5. Нажмите **«Готово»** — бот создан и отправлен на **модерацию**
6. Дождитесь уведомления о прохождении модерации
7. После модерации **получите токен бота**

Подробнее: [MAX для разработчиков — Создание чат-бота](https://dev.max.ru/docs/chatbots/bots-create)

### Nginx (обратный прокси)

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /webhook {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8787;
    }
}
```

## 📊 Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `MAX_BOT_TOKEN` | *(обяз.)* | Токен бота MAX (от business.max.ru) |
| `MAX_WEBHOOK_URL` | *(обяз.)* | Публичный URL для webhook (https://domain.com/webhook) |
| `MAX_WEBHOOK_SECRET` | *(пусто)* | Секрет для HMAC-верификации webhook |
| `MAX_API_BASE_URL` | `https://platform-api.max.ru` | Базовый URL MAX API |
| `MAX_ALLOWED_USERS` | *(пусто)* | Список разрешённых ID пользователей (через запятую) |
| `MAX_HOME_CHANNEL` | *(пусто)* | Chat ID для доставки cron/уведомлений |

Все переменные читаются при инициализации адаптера: **env → config.yaml → default**.

## 🚀 Запуск

### После установки

```bash
hermes gateway restart
```

Плагин автоматически:
1. Проверит валидность токена (GET /me)
2. Зарегистрирует команды бота (PATCH /me/commands)
3. Настроит webhook (POST /subscriptions)
4. Запустит локальный HTTP-сервер для приёма webhook

### Проверка работы

```bash
# Проверить health endpoint
curl https://your-domain.com/health

# Проверить логи Gateway
hermes gateway logs
```

### Long Polling (если нет публичного домена)

Плагин автоматически использует Long Polling как fallback, если webhook не зарегистрирован.

## 🚀 Использование

После подключения бот будет автоматически:
- Принимать сообщения от пользователей MAX
- Передавать их агенту Hermes
- Отправлять ответы обратно в MAX

В чате MAX появится кнопка вызова команд — нажмите её, чтобы увидеть `/start`, `/help`, `/about`.

### Inline keyboard

Агент может отправлять сообщения с кнопками:

```python
buttons = [
    [{"text": "Да", "payload": "yes"}, {"text": "Нет", "payload": "no"}]
]
```

Callback-кнопки поддерживаются: при нажатии плагин получает событие `message_callback` и передаёт payload агенту.

### Cron и уведомления

Настройте `MAX_HOME_CHANNEL` — и плагин сможет доставлять сообщения от Hermes (cron-задачи, уведомления, алерты) в указанный чат MAX.

## 📁 Структура проекта

```
max-hermes-plugin/
├── plugins/
│   └── platforms/
│       └── max/
│           ├── __init__.py          # Точка входа плагина (register)
│           ├── adapter.py           # Основной адаптер (MaxAdapter + webhook-сервер)
│           └── plugin.yaml          # Манифест плагина (версия, зависимости, env)
├── max_shared/
│   ├── __init__.py                  # Публичный API библиотеки
│   ├── constants.py                 # Константы (таймауты, URL, лимиты)
│   ├── converter.py                 # MessageConverter — конвертация сообщений
│   ├── markdown.py                  # Определение и обработка Markdown
│   ├── max_client.py                # MAXClient — HTTP-клиент для MAX Bot API
│   └── models.py                    # Pydantic-модели для MAX API
├── tests/
│   ├── __pycache__/
│   └── test_adapter.py              # Тесты адаптера
├── assets/                          # Графика для README
├── .github/
│   └── workflows/
│       └── ci.yml                   # GitHub Actions CI
├── banner.png                       # Баннер для README
├── CONTRIBUTING.md                  # Гайд по контрибьюции
├── LICENSE                          # MIT License
├── PRESS_RELEASE.md                 # Короткий пресс-релиз
├── PRESS_RELEASE_DETAIL.md          # Подробный пресс-релиз
├── PRESS_RELEASE_REDDIT.md          # Пресс-релиз для Reddit
├── README.md                        # Этот файл
├── requirements.txt                 # Зависимости Python
└── .gitignore
```

## 📊 Сравнение с Telegram Bot API

| Возможность | Telegram | MAX Bot API |
|-------------|----------|-------------|
| Webhook | ✅ | ✅ |
| Long Polling | ✅ | ✅ |
| Inline keyboard | ✅ | ✅ |
| Reply keyboard | ✅ | ❌ (только inline) |
| Callback buttons | ✅ | ✅ |
| Send/Edit/Delete messages | ✅ | ✅ |
| Typing indicator | ✅ | ✅ |
| Read receipts | ✅ | ❌ |
| **Bot commands menu** | ✅ | ✅ **(добавлено)** |
| Send images/files | ✅ | ✅ (через upload) |
| Send location | ✅ | ❓ |
| Send stickers | ✅ | ❓ |
| Group chats | ✅ | ✅ |
| Channels | ✅ | ✅ |

## 🧪 Тестирование

```bash
# Установка зависимостей для тестов
pip install pytest pytest-asyncio aiohttp pydantic pyyaml

# Запуск тестов
python -m pytest tests/ -v

# Проверка синтаксиса
python -m py_compile plugins/platforms/max/adapter.py
python -m py_compile plugins/platforms/max/__init__.py

# Валидация манифеста
python -c "import yaml; yaml.safe_load(open('plugins/platforms/max/plugin.yaml')); print('plugin.yaml OK')"
```

### CI

При каждом пуше в `main` или `develop` (и на PR) GitHub Actions автоматически:
- Запускает тесты на Python 3.11 и 3.12
- Проверяет синтаксис Python
- Валидирует `plugin.yaml`

## 🔧 Устранение неполадок

### Плагин не подключается

1. Проверьте, что Gateway поддерживает плагины: `hermes gateway status`
2. Убедитесь, что плагин склонирован в правильную папку: `~/.hermes/plugins/platforms/max/`
3. Проверьте логи Gateway: `hermes gateway logs`

### Плагин не получает сообщения от MAX

1. Проверьте регистрацию webhook: `curl -H "Authorization: ***" https://platform-api.max.ru/subscriptions`
2. Проверьте что порт открыт: `curl https://your-domain.com/health`
3. Убедитесь, что `MAX_WEBHOOK_URL` доступен из интернета

### Команды не отображаются в MAX

1. Проверьте, что плагин зарегистрировал команды при старте (логи Gateway)
2. Команды регистрируются на `platform-api2.max.ru` через `set_commands()`
3. Если команды не появились — перезапустите Gateway

### Hermes не отвечает

1. Проверьте, что Hermes запущен: `hermes --version`
2. Проверьте статус Gateway: `hermes gateway status`

### Бот не отвечает в MAX

1. Проверьте логи плагина на наличие ошибок
2. Убедитесь, что `MAX_BOT_TOKEN` валиден (проверьте через `curl https://platform-api.max.ru/me`)
3. Проверьте, что бот активирован и прошёл модерацию в MAX

## 📄 Recent Fixes

| # | Фикс | Файл |
|---|------|------|
| 1 | **Лишние префиксы ответов** — фильтр `remove_response_prefix` убирает `"You are Hermes Agent"`, `"Available tools:"`, `"Доступные инструменты:"` и `"Ты — Hermes Agent"` | `adapter.py` |
| 2 | **`attachments` → `Optional`** — Pydantic больше не падает, если MAX присылает `null`. Теперь `null` → `[]` до парсинга | `max_shared/models.py` |
| 3 | **ROLE_INSTRUCTION смягчён** — убран запрет инструментов и "1-3 предложения". Агент может отвечать как полноценный Hermes | `adapter.py` |
| 4 | **Bot Commands Menu** — регистрация `/start`, `/help`, `/about` через `PATCH /me/commands` + прямая обработка без Hermes | `adapter.py` |
| 5 | **HMAC-верификация** — проверка подписи webhook через HMAC-SHA256 (опционально) | `adapter.py` |
| 6 | **Дедупликация сообщений** — in-memory cache с таймаутом для исключения дублей от MAX API | `adapter.py` |

## 📄 Лицензия

MIT License. См. [LICENSE](LICENSE).

---

## 🔗 Связанные проекты

| Проект | Описание |
|--------|----------|
| [MAX Hermes Bridge](https://github.com/RuslanStrogov/max-hermes) | Python-мост между MAX Bot API и Hermes Agent через CLI. Поддерживает webhook, Docker, systemd. |
| [MAX Shared](https://github.com/RuslanStrogov/max-shared) | Общая библиотека: MAXClient, модели, конвертер, markdown |

## 📢 Пресс-релизы

Готовые тексты для публикации в сообществах и СМИ:

- [Короткий текст для Telegram-каналов](PRESS_RELEASE.md)
- [Подробный текст для Хабра/vc.ru/DTF](PRESS_RELEASE_DETAIL.md)
- [Пост для Reddit/Hacker News](PRESS_RELEASE_REDDIT.md)

<div align="center">

  <sub>🎨 Designed by <a href="https://br-design.ru/">BR-DESIGN</a></sub>

</div>

---

<div align="center">

  <sub>🇷🇺 Опенсорс — **Поддержи наш продукт** · <a href="https://br-design.ru/">BR-DESIGN</a></sub>

</div>