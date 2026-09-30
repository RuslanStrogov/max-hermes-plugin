# 💻 Разработка

> Как настроить окружение, запустить тесты и внести изменения.

## Требования

- Python 3.11+
- Hermes Agent (для интеграционного тестирования)

## Установка для разработки

```bash
git clone https://github.com/RuslanStrogov/max-hermes-plugin
cd max-hermes-plugin
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Тестирование

```bash
# unit tests
python -m pytest tests/ -v

# с coverage
python -m pytest tests/ --cov=max_shared --cov=plugins --cov-report=term-missing
```

## Структура проекта

```
max-hermes-plugin/
├── plugins/
│   └── max_adapter.py    # Плагин-адаптер для Hermes Agent
├── max_shared/            # Общая библиотека для MAX Bot API
│   ├── max_client.py      # HTTP-клиент для MAX API
│   ├── converter.py       # Конвертация сообщений MAX ↔ Hermes
│   ├── markdown.py        # Markdown-форматирование
│   └── constants.py       # Константы (типы чатов и пр.)
├── tests/
│   └── test_adapter.py    # Тесты адаптера
├── assets/                # Медиа-ресурсы
└── docs/                  # Документация
```

## Связанные проекты

- [max-hermes](https://github.com/RuslanStrogov/max-hermes) — Python-бридж между MAX Bot API и Hermes Agent
- [max-openclaw](https://github.com/RuslanStrogov/max-openclaw) — MAX Channel Plugin для OpenClaw