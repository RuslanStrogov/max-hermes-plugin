<div align="center">

  <img src="banner.png" alt="MAX Hermes Plugin Banner" width="100%"/>

  <br/>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/MAX-Bot%20API-6366F1?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iIzYzNjZmMSI+PHBhdGggZD0iTTEyIDJMMTggOEwxOCAyMkw2IDIyTDYgOEwxMiAyWiIvPjwvc3ZnPg==&logoColor=white" alt="MAX"/>
  <img src="https://img.shields.io/badge/Hermes-Agent-8B5CF6?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIiPjxwb2x5bGluZSBwb2ludHM9IjEzIDMgMTMgMTcgOCAxNyA4IDIxIDE2IDIxIDE2IDcgMjEgNyAyMSAzIDEzIDMiLz48L3N2Zz4=" alt="Hermes"/>
  <img src="https://img.shields.io/badge/Nginx-009639?logo=nginx&logoColor=white" alt="Nginx"/>
  <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions"/>
  <img src="https://img.shields.io/badge/Let's%20Encrypt-003A70?logo=letsencrypt&logoColor=white" alt="Let's Encrypt"/>
  <img src="https://img.shields.io/badge/License-MIT-22C55E" alt="MIT"/>

  <h3>Нативный платформенный плагин для <a href="https://hermes-agent.nousresearch.com">Hermes Agent</a></h3>
  <p>Подключает мессенджер <a href="https://max.ru">MAX</a> через Bot API — полная интеграция с AI-агентом</p>

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

- [Возможности](#-возможности)
- [Bot Commands Menu](#-bot-commands-menu)
- [Установка](#-установка)
- [Настройка](#-настройка)
- [Использование](#-использование)
- [Архитектура](#-архитектура)
- [Сравнение с Telegram Bot API](#-сравнение-с-telegram-bot-api)
- [Recent Fixes](#-recent-fixes)
- [Лицензия](#-лицензия)

---

## ✨ Возможности

| Фича | Статус |
|------|--------|
| Приём и отправка текстовых сообщений | ✅ |
| Bot Commands Menu (/start, /help, /about) | ✅ |
| Inline keyboard (кнопки с callback) | ✅ |
| Регистрация команд при старте (PATCH /me/commands) | ✅ |
| Обработка /команд без вызова Hermes | ✅ |
| Индикатор «Печатает...» | ✅ |
| Markdown-форматирование | ✅ |
| Белый список пользователей | ✅ |
| Webhook + Long Polling | ✅ |
| Отправка изображений (через upload API) | ✅ |

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

## 📦 Установка

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

## ⚙️ Настройка

### 1. Создайте бота в MAX

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

### 2. Настройте переменные окружения

```bash
# Добавьте в ~/.hermes/.env
MAX_BOT_TOKEN=your_bot_token_here
MAX_WEBHOOK_URL=https://your-domain.com/webhook
MAX_WEBHOOK_SECRET=your_secret
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

## 🏗️ Архитектура

```
┌──────────┐   webhook    ┌─────────────────┐   native    ┌──────────────┐
│          │ ──────────►  │                 │ ──────────►  │              │
│ MAX Bot  │              │ MAX Hermes      │              │ Hermes Agent │
│ API      │ ◄──────────  │ Plugin          │ ◄──────────  │              │
│          │  send_msg    │ (Python)        │  response    │              │
└──────────┘              └─────────────────┘              └──────────────┘
```

1. Пользователь пишет боту в MAX — в чате отображается кнопка вызова команд
2. MAX API отправляет webhook на плагин (или пользователь выбирает команду)
3. Плагин обрабатывает команды `/start`, `/help`, `/about` напрямую
4. Остальные сообщения передаются в Hermes Agent
5. Ответ Hermes отправляется обратно в MAX через Bot API

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
| Group chats | ✅ | ✅ |
| Channels | ✅ | ✅ |

## 📄 Recent Fixes

| # | Фикс | Файл |
|---|------|------|
| 1 | **`attachments` → `Optional`** — Pydantic больше не падает, если MAX присылает `null` | `max_shared/models.py` |
| 2 | **ROLE_INSTRUCTION смягчён** — убран запрет инструментов и "1-3 предложения". Агент может отвечать как полноценный Hermes | `adapter.py` |
| 3 | **Bot Commands Menu** — регистрация `/start`, `/help`, `/about` через `PATCH /me/commands` + прямая обработка без Hermes | `adapter.py` |

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