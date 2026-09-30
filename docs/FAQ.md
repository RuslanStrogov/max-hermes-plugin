# ❓ FAQ

## Часто задаваемые вопросы

### Чем отличается max-hermes-plugin от max-hermes?

`max-hermes-plugin` — нативный плагин для Hermes Agent,
устанавливается как plugin. `max-hermes` — отдельный Python-бридж,
работающий как самостоятельный сервис (webhook → Hermes API).

**Когда что использовать:**

| Сценарий | Решение |
|----------|---------|
| Работаете с Hermes Agent | `max-hermes-plugin` ✅ |
| Нужен лёгкий standalone-сервис | `max-hermes` |
| Работаете с OpenClaw | `max-openclaw` |

### Поддерживает ли плагин long polling?

Да, плагин поддерживает как webhook, так и long polling.

### Как добавить свои команды?

См. [API Reference](/docs/API.md) → Обработка команд.

### Есть ли поддержка изображений?

Да, отправка изображений через upload API поддерживается.