# 🚀 Деплой

> Установка max-hermes-plugin на сервер.

## Установка через pip

```bash
# Установка из репозитория
pip install git+https://github.com/RuslanStrogov/max-hermes-plugin.git
```

## Конфигурация Hermes Agent

Добавить в `~/.hermes/config.yaml`:

```yaml
plugins:
  - max_hermes_plugin

max:
  token: "ваш_токен_бота"
  webhook_url: "https://ваш-сервер.ru/webhook"
```

## Docker

См. [max-hermes — Docker setup](https://github.com/RuslanStrogov/max-hermes#docker)

## Nginx reverse proxy

```nginx
location /webhook {
    proxy_pass http://127.0.0.1:8787;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```