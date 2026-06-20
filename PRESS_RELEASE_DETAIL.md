# Подробный пресс-релиз для Хабра / vc.ru / DTF

## Как я подключил AI-агента Hermes к мессенджеру MAX — и открыл исходный код

### Проблатема

MAX — российский мессенджер с Bot API, похожим на Telegram. Но если в Telegram есть готовые библиотеки и интеграции почти для всего, то экосистема MAX пока молодая. Особенно когда речь идёт о подключении AI-агентов.

Я использую [Hermes Agent](https://hermes-agent.nousresearch.com) — мощную платформу для работы с AI-агентами (аналог Claude Desktop / OpenClaw, но с открытым исходным кодом). Hermes умеет работать с Telegram, Discord, Slack и другими платформами. Но не с MAX.

### Решение

Создал два проекта:

**1. max-hermes — Python-мост (standalone daemon)**

MAX Bot API → Webhook → FastAPI-сервер → Hermes CLI → ответ обратно в MAX

Мост принимает webhook-и от MAX, вызывает Hermes Agent через CLI, и отправляет ответ обратно через Bot API. Поддерживает:
- Inline keyboard и callback-кнопки
- Индикатор «Печатает...»
- Скачивание и отправку вложений
- Редактирование и удаление сообщений
- Белый список пользователей
- Docker, systemd, CI/CD с автодеплоем

**2. max-hermes-plugin — нативный плагин Hermes Gateway**

Прямая интеграция MAX в Hermes без промежуточного моста. Плагин регистрирует MAX как платформу в Hermes, и агент работает с MAX нативно — с поддержкой send_message, cron, sessions и других возможностей Hermes.

### Технологии

- Python 3.11+, FastAPI, httpx
- Hermes Agent CLI / Plugin API
- MAX Bot API (webhook, long polling, upload)
- Docker, systemd, GitHub Actions

### Сравнение подходов

| | max-hermes (мост) | max-hermes-plugin (плагин) |
|---|---|---|
| Установка | Отдельный сервер | Встраивается в Hermes |
| Зависимости | FastAPI + Hermes CLI | Только Hermes |
| Возможности MAX | Полные | Полные |
| Возможности Hermes | Через CLI | Нативные (cron, sessions) |
| Сложность | Средняя | Низкая |

### Ссылки

- max-hermes: https://github.com/RuslanStrogov/max-hermes
- max-hermes-plugin: https://github.com/RuslanStrogov/max-hermes-plugin

Оба проекта под лицензией MIT. Буду рад фидбеку и контрибуциям.
