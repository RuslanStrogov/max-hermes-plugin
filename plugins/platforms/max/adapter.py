"""MAX Bot API Platform Adapter for Hermes Agent.

A plugin-based gateway adapter that connects to the MAX messenger (max.ru)
via Bot API webhooks. Receives incoming messages as HTTP POST, sends
responses via MAX Bot API.

Supports:
- Text messages (Markdown formatting)
- Inline keyboards (callback buttons)
- Typing indicators
- File/image upload via MAX upload API
- User access control (allowlist)
- Long polling fallback
- Message deduplication

Configuration in config.yaml:

    platforms:
      max:
        enabled: true
        extra:
          token: "YOUR_BOT_TOKEN"
          webhook_url: "https://your-domain.com/webhook"
          webhook_secret: "optional-secret-for-hmac"
          api_base_url: "https://platform-api.max.ru"
          allowed_users: []           # empty = allow all
          home_channel: ""            # chat ID for cron delivery

Environment variables (all read at adapter construct time, env wins over config.yaml):

    MAX_BOT_TOKEN           Bot token from MAX partner platform (required)
    MAX_WEBHOOK_URL          Public URL for webhook (required)
    MAX_WEBHOOK_SECRET       HMAC secret for webhook verification (optional)
    MAX_API_BASE_URL         API base URL (default: https://platform-api.max.ru)
    MAX_ALLOWED_USERS        Comma-separated allowed user IDs (empty = all)
    MAX_HOME_CHANNEL         Chat ID for cron/notification delivery
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None  # type: ignore[assignment]

try:
    from aiohttp import web
except ImportError:
    web = None  # type: ignore[assignment]

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.session import SessionSource

from max_shared.constants import (
    DEFAULT_API_BASE_URL,
    DEDUP_MAX_SIZE,
    DEDUP_WINDOW_SECONDS,
    MAX_MESSAGE_LENGTH,
)
from max_shared.converter import MessageConverter
from max_shared.markdown import has_markdown
from max_shared.max_client import MAXClient, MAXApiError

logger = logging.getLogger(__name__)

DEFAULT_COMMANDS = [
    {"name": "start", "description": "Начать диалог с ботом"},
    {"name": "help", "description": "Помощь и информация о боте"},
]

COMMAND_RESPONSES = {
    "/start": "👋 Привет! Я бот Hermes Agent на платформе MAX. Готов помогать!\n\nНажми на кнопку с командами у поля ввода или отправь /help.",
    "start": "👋 Привет! Я бот Hermes Agent на платформе MAX. Готов помогать!\n\nНажми на кнопку с командами у поля ввода или отправь /help.",
    # /help намеренно НЕ перехватываем — справку отдаёт сам Hermes
    # (полный список команд и скиллов).
}

# ── Русская локализация служебных статусов ─────────────────────────────────
# MAX — русскоязычный мессенджер, поэтому этапы работы и технические детали
# прогресса показываем по-русски. Замены узкие и однозначные, чтобы не
# задевать обычный текст ответов агента.
_STATUS_SUBS = (
    (re.compile(r"⏳ Working — (\d+) min"), r"⏳ Работаю — \1 мин"),
    (re.compile(r"⏩ Steered into current run"), "⏩ Сообщение добавлено в текущий запуск"),
    (re.compile(r"⚡ Interrupting current task"), "⚡ Прерываю текущую задачу"),
    (re.compile(r"\biteration (\d+)/(\d+)"), r"итерация \1/\2"),
    (re.compile(r"\breceiving stream response\b"), "получаю ответ модели"),
    (re.compile(r"\bwaiting for non-streaming API response\b"), "жду ответ API"),
    (re.compile(r"\bwaiting for provider response \(streaming\)\b"), "жду ответ провайдера"),
)

_STATUS_PHRASES = {
    "still on it": "всё ещё работаю",
    "still working through it": "продолжаю работу",
    "waiting for the result": "жду результат",
    "on it": "делаю",
    "one sec": "секунду",
    "checking that now": "проверяю",
}

_TOOL_NAMES_RU = {
    "terminal": "терминал",
    "read_file": "чтение файла",
    "write_file": "запись файла",
    "patch": "правка файла",
    "search_files": "поиск в файлах",
    "web_search": "поиск в интернете",
    "web_extract": "чтение страниц",
    "browser_navigate": "браузер",
    "vision_analyze": "анализ изображения",
    "delegate_task": "подзадача",
    "todo": "план",
    "memory": "память",
    "execute_code": "выполняю код",
    "cronjob": "крон",
    "image_generate": "генерация изображения",
    "text_to_speech": "синтез речи",
    "skill_view": "навык",
    "skills_list": "список навыков",
    "clarify": "уточняю",
}

# Русские описания команд в меню у поля ввода.
# Реестр Hermes отдаёт английские формулировки; для MAX переводим.
# Незнакомые команды (в т.ч. добавленные позже) остаются с исходным текстом.
_MENU_DESC_RU = {
    "help": "Справка по командам",
    "new": "Начать новый диалог",
    "stop": "Остановить фоновые процессы",
    "status": "Состояние сессии, модель, контекст",
    "resume": "Продолжить сохранённый диалог",
    "sessions": "Список и продолжение диалогов",
    "model": "Сменить модель",
    "debug": "Отчёт для отладки (система и логи)",
    "restart": "Перезапустить шлюз",
    "update": "Обновить Hermes до новой версии",
    "commands": "Все команды и навыки",
    "approve": "Подтвердить опасную команду",
    "deny": "Отклонить опасную команду",
    "queue": "Поставить запрос в очередь",
    "steer": "Вмешаться в текущий запуск",
    "background": "Запустить запрос в фоне",
    "reasoning": "Уровень рассуждений и показ",
    "usage": "Расход токенов и лимиты",
    "platform": "Пауза, запуск и список платформ",
    "profile": "Текущий профиль и каталог",
    "whoami": "Мои права на команды",
    "start": "Приветствие",
    "topic": "Темы в личных сообщениях",
    "retry": "Повторить последнее сообщение",
    "undo": "Откатить N шагов и переспросить",
    "title": "Задать название диалога",
    "branch": "Ветвление диалога",
    "compress": "Сжать контекст беседы",
    "rollback": "Точки восстановления файлов",
    "agents": "Активные агенты и задачи",
    "goal": "Постоянная цель для работы",
    "moa": "Запрос через смесь моделей",
}

# Role instruction prepended to every user message
ROLE_INSTRUCTION = (
    "[Системные инструкции]\n"
    "Ты — MAX Bot. Общайся на русском. Будь полезным.\n"
    "[/Системные инструкции]\n\n"
)


def _get_env_or_extra(
    config: PlatformConfig, key: str, extra_key: str, default: str = ""
) -> str:
    """Read from env var first, then config.yaml extra, then default."""
    val = os.getenv(key, "")
    if val:
        return val.strip()
    val = config.extra.get(extra_key, default)
    if isinstance(val, str):
        return val.strip()
    return str(val) if val else default


def _parse_allowed_users(config: PlatformConfig) -> Set[int]:
    """Parse allowed user IDs from env or config."""
    raw = _get_env_or_extra(config, "MAX_ALLOWED_USERS", "allowed_users", "")
    if not raw:
        return set()
    users = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                users.add(int(part))
            except ValueError:
                logger.warning("Invalid user ID in allowed_users: %s", part)
    return users


def _verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from MAX webhook."""
    if not secret or not signature:
        return True
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class MaxAdapter(BasePlatformAdapter):
    """MAX Bot API platform adapter for Hermes Agent.

    Uses shared max_shared library for API client, models, and converter.
    This adapter focuses on the plugin integration layer:
    - Webhook server lifecycle
    - Message dispatch to Hermes gateway
    - Deduplication
    - Access control
    """

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.MAX)
        self._token = _get_env_or_extra(config, "MAX_BOT_TOKEN", "token", "")
        self._webhook_url = _get_env_or_extra(
            config, "MAX_WEBHOOK_URL", "webhook_url", ""
        )
        self._webhook_secret = _get_env_or_extra(
            config, "MAX_WEBHOOK_SECRET", "webhook_secret", ""
        )
        self._api_base_url = _get_env_or_extra(
            config, "MAX_API_BASE_URL", "api_base_url", DEFAULT_API_BASE_URL
        )
        self._question_separator = _get_env_or_extra(
            config, "MAX_QUESTION_SEPARATOR", "question_separator", "."
        )
        self._allowed_users = _parse_allowed_users(config)
        self._bot_username = _get_env_or_extra(
            config, "MAX_BOT_USERNAME", "bot_username", "se13320221_1_bot"
        ).lstrip("@").lower()
        self._trigger_words = [
            w.strip().lower()
            for w in _get_env_or_extra(
                config, "MAX_TRIGGER_WORDS", "trigger_words", ""
            ).split(",")
            if w.strip()
        ]
        self._home_channel = _get_env_or_extra(
            config, "MAX_HOME_CHANNEL", "home_channel", ""
        )
        self._client: Optional["MAXClient"] = None
        self._connected = False

        # Dedup
        self._seen_ids: Set[str] = set()
        self._dedup_lock = asyncio.Lock()

        # Polling
        self._polling_task: Optional[asyncio.Task] = None
        self._polling_stop = asyncio.Event()
        self._last_message_ids: Dict[str, str] = {}
        # Индикатор «Печатает...» — периодическая задача на чат
        self._typing_tasks: Dict[str, asyncio.Task] = {}
        # Состояние интерактивных кнопок: clarify_id / confirm_id -> session_key.
        # Нужно, чтобы нажатие кнопки резолвило именно тот prompt, из которого
        # она была отрисована (см. send_clarify / send_slash_confirm).
        self._clarify_state: Dict[str, str] = {}
        self._slash_confirm_state: Dict[str, str] = {}
        # Вебхук-сервер
        self._app: Any = None
        self._runner: Any = None
        self._site: Any = None

        if not AIOHTTP_AVAILABLE:
            raise ImportError(
                "aiohttp is required for MAX adapter. Install: pip install aiohttp"
            )

        if not self._token:
            raise ValueError("MAX_BOT_TOKEN is required")
        if not self._webhook_url:
            raise ValueError("MAX_WEBHOOK_URL is required")

    @property
    def platform_name(self) -> str:
        return "max"

    # MAX Bot API: не более 32 команд в меню, описание ≤128 символов.
    MAX_MENU_COMMANDS = 32

    def _build_menu_commands(self) -> List[Dict[str, str]]:
        """Собрать меню команд бота из единого реестра Hermes.

        Меню в MAX (кнопка списка команд у поля ввода) строится из
        зарегистрированных команд. Берём их из того же реестра, что и
        Telegram-меню, чтобы список не расходился с реальными командами.
        При недоступности реестра откатываемся на DEFAULT_COMMANDS.
        """
        pairs: List[tuple] = []
        try:
            from hermes_cli.commands import telegram_menu_commands
            pairs, _hidden = telegram_menu_commands(
                max_commands=self.MAX_MENU_COMMANDS
            )
        except Exception as e:
            logger.warning("Не удалось прочитать реестр команд Hermes: %s", e)

        if not pairs:
            return [dict(c) for c in DEFAULT_COMMANDS]

        out: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for name, desc in pairs:
            clean = str(name).strip().lstrip("/")
            if not clean or clean in seen:
                continue
            seen.add(clean)
            desc_ru = _MENU_DESC_RU.get(clean)
            out.append({
                "name": clean,
                "description": str(desc_ru or desc)[:128],
            })
            if len(out) >= self.MAX_MENU_COMMANDS:
                break
        return out

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Start webhook server and register webhook with MAX."""
        try:
            self._client = MAXClient(
                token=self._token,
                base_url=self._api_base_url,
            )

            # Verify bot info
            bot_info = await self._client.get_bot_info()
            if not bot_info:
                logger.error("Failed to get bot info — check MAX_BOT_TOKEN")
                return False
            # Свой user_id — чтобы не отвечать на собственные сообщения
            self._bot_user_id = bot_info.get("user_id", 0)
            logger.info("Connected to MAX as: %s (user_id=%s)", bot_info.get("name", "unknown"), self._bot_user_id)

            # Register bot commands (menu button)
            try:
                cmds = self._build_menu_commands()
                await self._client.set_commands(cmds)
                logger.info("Bot commands registered: %d commands", len(cmds))
            except Exception as e:
                logger.warning("Failed to register bot commands: %s (non-fatal)", e)

            # Register webhook (skip on reconnect if already registered)
            if not is_reconnect:
                sub_result = await self._client.subscribe(url=self._webhook_url)
                if sub_result:
                    logger.info("Webhook registered: %s", self._webhook_url)
                else:
                    logger.warning("Webhook registration failed — may already be registered")

            # Start local webhook server
            await self._start_webhook_server()

            # Start long-polling fallback
            self._polling_stop = asyncio.Event()
            self._polling_task = asyncio.create_task(self._polling_loop())
            logger.info("Long-polling fallback started")

            self._connected = True
            return True

        except Exception as e:
            logger.error("Failed to connect: %s", e, exc_info=True)
            return False

    async def disconnect(self):
        """Stop webhook server and polling."""
        self._connected = False
        self._polling_stop.set()
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("Disconnected")

    async def _start_webhook_server(self):
        """Start aiohttp webhook server."""
        async def handle_webhook(request: web.Request) -> web.Response:
            body = await request.read()
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid JSON"}, status=400)

            # Verify signature
            sig = request.headers.get("X-Hub-Signature-256", "")
            if self._webhook_secret and not _verify_webhook_signature(body, sig, self._webhook_secret):
                logger.warning("Invalid webhook signature")
                return web.json_response({"error": "Invalid signature"}, status=403)

            asyncio.ensure_future(self._handle_update(data))
            return web.json_response({"ok": True})

        async def handle_health(request: web.Request) -> web.Response:
            return web.json_response({"status": "ok", "platform": "max"})

        self._app = web.Application()
        self._app.router.add_post("/webhook", handle_webhook)
        self._app.router.add_get("/health", handle_health)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        parsed = urlparse(self._webhook_url)
        port = parsed.port or int(os.environ.get("MAX_LOCAL_PORT", "8787"))

        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Webhook server listening on port %d", port)

    async def _handle_update(self, data: Dict):
        """Handle incoming update from MAX."""
        update_type = data.get("update_type", "")

        # Dedup
        msg_id = (
            data.get("message", {}).get("body", {}).get("mid", "")
            if data.get("message")
            else ""
        )
        if msg_id and self._is_dedup(msg_id):
            return

        if update_type == "message_created":
            await self._handle_message_created(data)
        elif update_type == "message_callback":
            await self._handle_message_callback(data)
        else:
            logger.debug("Unhandled update type: %s", update_type)

    def _should_reply(self, text: str, user_id: int = 0, chat_type: str = "dialog") -> bool:
        """Проверяет, нужно ли отвечать (упомянут бот, триггер-слова, allowed_users)."""
        if not text:
            return False
        # Не отвечаем на свои же сообщения (защита от эхо)
        bot_self_id = int(os.environ.get("MAX_BOT_SELF_ID", "0")) or \
            getattr(self, '_bot_user_id', 0)
        if bot_self_id and user_id == bot_self_id:
            logger.info("Self-msg ignored: user_id=%s == bot_self_id", user_id)
            return False
        # В личных чатах (dialog) отвечаем всегда
        if chat_type in ("dialog",):
            return True
        # Слэш-команды из меню бота должны работать и в группах: MAX
        # присылает "/команда" без упоминания бота, поэтому обычная проверка
        # на mention/триггер-слово их бы отсекла. Гейтинг самих команд —
        # на стороне Hermes (у части команд свои права доступа).
        if text.lstrip().startswith("/"):
            return True
        # Всегда отвечаем разрешённым пользователям
        if self._allowed_users and user_id in self._allowed_users:
            return True
        # Отвечаем если упомянут бот (@username)
        low = text.lower()
        if self._bot_username and f"@{self._bot_username}" in low:
            return True
        # Отвечаем по триггер-словам (бот, ии, интеллект, робот...)
        for w in self._trigger_words:
            if w in low:
                return True
        return False

    def _is_dedup(self, msg_id: str) -> bool:
        """Проверяет, не обрабатывали ли мы это сообщение ранее."""
        if not msg_id:
            return False
        if msg_id in self._seen_ids:
            logger.debug("Dedup: %s", msg_id)
            return True
        self._seen_ids.add(msg_id)
        if len(self._seen_ids) > DEDUP_MAX_SIZE:
            self._seen_ids.pop()
        return False

    async def _polling_loop(self):
        """Fallback long-polling loop for receiving messages."""
        offset = 0
        while not self._polling_stop.is_set():
            try:
                updates = await self._client.get_updates(
                    offset=offset,
                    limit=100,
                    timeout=30,
                )
                if updates:
                    for update in updates:
                        await self._handle_update(update)
                        mid = (
                            update.get("message", {}).get("body", {}).get("mid", "")
                            if update.get("message")
                            else ""
                        )
                        if mid:
                            try:
                                offset = max(offset, int(mid))
                            except (ValueError, TypeError):
                                pass
            except asyncio.CancelledError:
                break
            except MAXApiError as e:
                if e.code in ("forbidden", "unauthorized"):
                    logger.error("Polling failed: %s -- stopping", e)
                    break
                logger.warning("Polling API error: %s (retrying in 5s)", e)
                await asyncio.sleep(5)
            except asyncio.TimeoutError:
                # Long-poll timeout — normal, just retry immediately
                continue
            except Exception as e:
                _msg = str(e).strip()
                if _msg:
                    logger.warning("Polling error: %s (retrying in 15s)", _msg)
                else:
                    logger.debug("Polling empty error (timeout?) — retrying")
                await asyncio.sleep(15)


    def _start_typing(self, chat_id: str):
        """Запускает периодическую отправку «Печатает...» для чата."""
        self._stop_typing(chat_id)
        try:
            self._typing_tasks[chat_id] = asyncio.create_task(self._keep_typing(chat_id))
        except RuntimeError:
            pass

    def _stop_typing(self, chat_id: str):
        """Останавливает индикатор «Печатает...» для чата."""
        task = self._typing_tasks.pop(chat_id, None)
        if task:
            try:
                task.cancel()
            except Exception:
                pass

    async def _keep_typing(self, chat_id: str):
        """Отправляет индикатор каждые 4 секунды, пока не отменят."""
        try:
            while True:
                if self._client:
                    try:
                        await self.send_typing(chat_id)
                    except Exception as e:
                        logger.debug("send_typing failed for %s: %s", chat_id, e)
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _handle_message_created(self, data: Dict):
        """Process incoming text message from MAX."""
        logger.info("HMC: ENTERED _handle_message_created update_type=%s", data.get("update_type", "??"))
        msg = data.get("message", {})
        sender = msg.get("sender", {})
        recipient = msg.get("recipient", {})
        body = msg.get("body", {})

        user_id = sender.get("user_id", 0)
        chat_id = recipient.get("chat_id", 0)
        # Определяем тип чата: "chat_type" или "type", по умолчанию dialog
        chat_type = (
            recipient.get("chat_type") or recipient.get("type") or "dialog"
        )
        # Для индикатора «печатает...» нужен РЕАЛЬНЫЙ chat_id чата: действия
        # (/chats/{id}/actions) адресуются по chat_id, а не по user_id.
        # Для ответов в ЛС ниже chat_id подменяется на user_id, но для
        # статусов сохраняем исходный идентификатор чата.
        typing_chat_id = chat_id
        # В группах ID отрицательный — не заменяем на user_id
        if chat_type == "dialog" and chat_id >= 0:
            chat_id = user_id
        # Отладка
        logger.info(
            "HMC: chat_id=%s chat_type=%s type=%s user_id=%s",
            chat_id, chat_type, recipient.get("type"), user_id
        )
        text = body.get("text", "")

        # Handle bot commands directly (without Hermes)
        command_text = text.strip().lower() if text else ""
        if command_text in COMMAND_RESPONSES:
            response_text = COMMAND_RESPONSES[command_text]
            if self._client:
                try:
                    original_mid = body.get("mid")
                    await self._client.send_message(
                        chat_id=chat_id,
                        user_id=None,
                        text=response_text,
                        format="markdown",
                        reply_to=original_mid,
                    )
                except Exception as e:
                    logger.warning("Failed to send command response: %s", e)
            return

        if self._allowed_users and user_id not in self._allowed_users:
            logger.warning("Unauthorized user %d — ignoring", user_id)
            return

        # Check if we should reply
        if not self._should_reply(text, user_id=user_id, chat_type=chat_type):
            return

        user_name = sender.get("name", sender.get("first_name", "Unknown"))
        text_with_role = f"{ROLE_INSTRUCTION}{text}" if text else ROLE_INSTRUCTION.rstrip("\n")
        event = MessageEvent(
            message_id=body.get("mid", str(uuid.uuid4())),
            text=text_with_role,
            source=SessionSource(
                platform=self.platform,
                chat_id=str(chat_id),
                user_id=str(user_id),
                user_name=user_name,
            ),
            timestamp=datetime.fromtimestamp(
                msg.get("timestamp", int(time.time() * 1000)) / 1000
            ),
        )

        # Запускаем периодический индикатор «Печатает...» (по РЕАЛЬНОМУ chat_id)
        self._start_typing(str(typing_chat_id))

        # Принудительно чистим зависшие relay-сессии перед диспатчем
        if hasattr(self, '_active_sessions'):
            for k in list(self._active_sessions.keys()):
                if 'agent:main:relay' in k:
                    try:
                        self._active_sessions.pop(k, None)
                        self._pending_messages.pop(k, None)
                        self._session_tasks.pop(k, None)
                    except Exception:
                        pass
        logger.info("DMP: dispatching msg chat=%s text=%s handler=%s", str(chat_id), text[:30], bool(getattr(self, '_message_handler', None)))
        # Прямой вызов _message_handler в обход session guard
        if hasattr(self, '_message_handler') and self._message_handler is not None:
            try:
                logger.info("DMP: _message_handler CALLED for %s", str(chat_id))
                _resp = await self._message_handler(event)
                # _message_handler возвращает текст ответа — отправляем его
                if _resp and isinstance(_resp, str):
                    await self.send(str(chat_id), _resp)
            except Exception as e:
                logger.error("DMP: _message_handler failed: %s", e, exc_info=True)
        else:
            try:
                await self.handle_message(event)
            except Exception as e:
                logger.error("DMP: handle_message failed: %s", e, exc_info=True)
        # Запоминаем chat_id для прямого пуллинга сообщений (реальный chat_id чата)
        self._last_message_ids[str(typing_chat_id)] = body.get("mid", "")
        # Останавливаем индикатор «Печатает...»
        self._stop_typing(str(typing_chat_id))

    async def _handle_message_callback(self, data: Dict):
        """Handle callback from inline keyboard button."""
        callback = data.get("callback", {})
        msg = data.get("message", {})
        sender = msg.get("sender", {}) if msg else {}
        recipient = msg.get("recipient", {}) if msg else {}

        user_id = sender.get("user_id", 0)
        chat_id = recipient.get("chat_id", 0)
        chat_type = recipient.get("type", "dialog")
        callback_payload = callback.get("payload", "")
        button_text = callback.get("text", "")

        if self._allowed_users and user_id not in self._allowed_users:
            return

        # Нажатие кнопки clarify/подтверждения обрабатываем адресно, чтобы
        # резолвить именно тот prompt, из которого отрисована клавиатура.
        if callback_payload and await self._resolve_button_payload(callback_payload, str(chat_id)):
            return

        user_name = sender.get("name", sender.get("first_name", "Unknown"))
        text = f"[Кнопка: {button_text}]\nPayload: {callback_payload}"

        event = MessageEvent(
                    message_id=str(uuid.uuid4()),
                    text=text,
                    source=SessionSource(
                        platform=self.platform,
                        chat_id=str(chat_id),
                        user_id=str(user_id),
                        user_name=user_name,
                    ),
                    timestamp=datetime.fromtimestamp(
                        time.time()
                    ),
                )

        # Запускаем периодический индикатор «Печатает...»
        self._start_typing(str(chat_id))

        # Прямой вызов _message_handler в обход session guard
        if hasattr(self, '_message_handler') and self._message_handler is not None:
            try:
                await self._message_handler(event)
            except Exception as e:
                logger.error("Callback message handler failed: %s", e, exc_info=True)
        else:
            try:
                await self.handle_message(event)
            except Exception as e:
                logger.error("Callback handle_message failed: %s", e, exc_info=True)
        # Останавливаем индикатор «Печатает...»
        self._stop_typing(str(chat_id))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get basic chat info."""
        return {"name": chat_id, "type": "max"}

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SendResult:
        """Send a text message to MAX."""
        if not content:
            return SendResult(success=False, error="Empty message")

        if len(content) > MAX_MESSAGE_LENGTH:
            content = content[: MAX_MESSAGE_LENGTH - 3] + "..."

        # Служебные статусы и прогресс — по-русски
        content = self._ru_status(content)

        payload: Dict[str, Any] = {"text": content}

        if has_markdown(content):
            payload["format"] = "markdown"

        if reply_to:
            payload["reply_to"] = reply_to

        buttons = (metadata or {}).get("buttons")
        if buttons:
            payload["attachments"] = [
                MessageConverter.build_inline_keyboard(buttons)
            ]

        user_id = (metadata or {}).get("user_id")
        params: Dict[str, Any] = {}
        if user_id:
            params["user_id"] = str(user_id)
        elif chat_id:
            # MAX API: для личных сообщений используем user_id вместо chat_id
            try:
                cid = int(chat_id)
                if cid > 0:
                    params["user_id"] = str(cid)
                else:
                    params["chat_id"] = str(cid)
            except (ValueError, TypeError):
                params["chat_id"] = str(chat_id)
        else:
            return SendResult(success=False, error="No chat_id or user_id provided")

        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/messages?{query}" if query else "/messages"

        logger.info("MAX send: %s text_len=%d", path, len(content))
        result = await self._client._request("POST", path, data=payload)
        if result:
            mid = result.get("message", {}).get("body", {}).get("mid", "")
            if chat_id:
                self._last_message_ids[chat_id] = mid
            logger.info("MAX send SUCCESS: mid=%s", mid)
            return SendResult(
                success=True,
                message_id=mid,
            )
        logger.error("MAX send FAILED: no result from API")
        return SendResult(success=False, error="Failed to send message")

    # MAX принимает только эти статусы активности. typing_off / typing дают
    # 400 proto.payload — их не отправляем.
    SUPPORTED_ACTIONS = {
        "typing_on",
        "sending_photo",
        "sending_video",
        "sending_file",
        "sending_audio",
        "mark_seen",
    }

    async def send_action(self, chat_id: str, action: str) -> None:
        """Показать статус активности в чате («печатает…», «отправляет фото…»).

        Best-effort: любой сбой глотается, статус не должен ломать доставку.
        Действие адресуется РЕАЛЬНЫМ chat_id чата (а не user_id) — иначе MAX
        принимает запрос, но индикатор не показывает.
        """
        if not self._client or action not in self.SUPPORTED_ACTIONS:
            return
        try:
            await self._client.send_chat_action(chat_id=int(chat_id), action=action)
        except Exception as e:
            logger.debug("send_action(%s) failed for %s: %s", action, chat_id, e)

    async def send_typing(self, chat_id: str):
        """Send typing indicator."""
        logger.info("send_typing to chat_id=%s", chat_id)
        await self.send_action(chat_id, "typing_on")

    def _ru_status(self, text: str) -> str:
        """Перевести служебные статусы и прогресс на русский.

        Трогаем только узнаваемые служебные строки (пульс «Работаю», счётчик
        итераций, названия инструментов, короткие фразы-статусы). Обычный
        текст ответов агента не переписываем.
        """
        if not text:
            return text
        out = text
        for pat, repl in _STATUS_SUBS:
            out = pat.sub(repl, out)
        stripped = out.strip()
        if stripped in _STATUS_PHRASES:
            return _STATUS_PHRASES[stripped]
        lines = []
        for line in out.split("\n"):
            # строка вида "<emoji> <tool_name>"
            m = re.fullmatch(r"([^\w\s]+\s+)([a-z_]+)", line.strip())
            if m and m.group(2) in _TOOL_NAMES_RU:
                lines.append(f"{m.group(1)}{_TOOL_NAMES_RU[m.group(2)]}")
                continue
            # хвост вида "⏳ Работаю — 3 мин — terminal" в служебной строке
            m2 = re.search(r"(—\s+)([a-z_]+)\s*$", line)
            if (
                m2
                and m2.group(2) in _TOOL_NAMES_RU
                and line.lstrip()[:1] in ("⏳", "⚡", "⏩")
            ):
                line = line[: m2.start(2)] + _TOOL_NAMES_RU[m2.group(2)]
            lines.append(line)
        return "\n".join(lines)

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
        **kwargs: Any,
    ) -> SendResult:
        """Обновить ранее отправленное сообщение (PUT /messages/{id}).

        Нужно ядру: «пульс» прогресса и строки инструментов обновляются
        на месте, а не присылаются новым сообщением на каждое изменение.
        Без этого метода ядро падает в fallback и каждый апдейт становится
        отдельным сообщением.
        """
        if not self._client or not content:
            return SendResult(success=False, error="Not connected or empty")
        text = self._ru_status(content)
        fmt = "markdown" if has_markdown(text) else None
        # mid в MAX — строка вида "mid.000000001da5fea2...", не число.
        mid = str(message_id).strip()
        if not mid:
            return SendResult(success=False, error="Bad message_id")
        try:
            await self._client.edit_message(mid, text, format=fmt)
            return SendResult(success=True, message_id=mid)
        except Exception as e:
            logger.debug("edit_message failed (%s): %s", mid, e)
            return SendResult(success=False, error=str(e))

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Удалить сообщение (DELETE /messages?message_id=<mid>).

        Используется ядром для уборки служебных «пузырей» прогресса
        после успешного финального ответа.
        """
        if not self._client:
            return False
        mid = str(message_id).strip()
        if not mid:
            return False
        try:
            await self._client.delete_message(mid)
            return True
        except Exception as e:
            logger.debug("delete_message failed (%s): %s", mid, e)
            return False

    async def _send_inline_buttons(
        self,
        chat_id: str,
        text: str,
        buttons: List[List[Dict[str, str]]],
        reply_to: Optional[str] = None,
    ) -> SendResult:
        """Отправить сообщение с инлайновой клавиатурой MAX.

        MAX ждёт клавиатуру как attachment типа ``inline_keyboard``:
        ``{"type": "inline_keyboard", "payload": {"buttons": [[...]]}}``.
        Кнопка — ``{"type": "callback", "text": "...", "payload": "..."}``.
        """
        if not self._client:
            return SendResult(success=False, error="Not connected")
        payload: Dict[str, Any] = {
            "text": text,
            "attachments": [
                {"type": "inline_keyboard", "payload": {"buttons": buttons}}
            ],
        }
        if reply_to:
            payload["reply_to"] = reply_to
        try:
            cid = int(chat_id)
        except (ValueError, TypeError):
            return SendResult(success=False, error="Bad chat_id")
        query = f"user_id={cid}" if cid > 0 else f"chat_id={cid}"
        try:
            result = await self._client._request("POST", f"/messages?{query}", data=payload)
            mid = ((result or {}).get("message") or {}).get("body", {}).get("mid", "")
            logger.info("MAX inline buttons sent: mid=%s", mid)
            return SendResult(success=True, message_id=mid)
        except Exception as e:
            logger.error("MAX inline buttons error: %s", e)
            return SendResult(success=False, error=str(e))

    async def send_clarify(
        self,
        chat_id: str,
        question: str,
        choices: Optional[list],
        clarify_id: str,
        session_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Clarify-промпт с инлайновыми кнопками (по одной на вариант).

        Gateway вызывает этот хук, когда агент задаёт вопрос через clarify с
        вариантами. Без override'а базовый класс отдаёт нумерованный список
        текстом — именно поэтому кнопки раньше не появлялись.

        Нажатие кнопки приходит в ``_handle_message_callback`` с payload
        ``cl:<clarify_id>:<idx>`` и резолвится через
        ``tools.clarify_gateway.resolve_gateway_clarify``.
        """
        reply_to = (metadata or {}).get("reply_to")
        text = f"❓ {question}"
        if choices:
            option_lines = "\n".join(
                f"{i}. {c}" for i, c in enumerate(choices, start=1)
            )
            text += f"\n\n{option_lines}"

        if not choices:
            # Открытый вопрос: просто текст, следующий ответ перехватит gateway.
            return await self.send(chat_id, text, reply_to=reply_to)

        buttons: List[List[Dict[str, str]]] = []
        for idx, choice in enumerate(choices):
            label = str(choice)
            if len(label) > 60:
                label = label[:57] + "..."
            buttons.append([{
                "type": "callback",
                "text": label,
                "payload": f"cl:{clarify_id}:{idx}",
            }])
        buttons.append([{
            "type": "callback",
            "text": "✏️ Свой вариант",
            "payload": f"cl:{clarify_id}:other",
        }])

        self._clarify_state[clarify_id] = session_key
        return await self._send_inline_buttons(chat_id, text, buttons, reply_to)

    async def send_slash_confirm(
        self,
        chat_id: str,
        title: str,
        message: str,
        session_key: str,
        confirm_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Три кнопки подтверждения дорогой слэш-команды.

        Нажатие приходит как payload ``sc:<once|always|cancel>:<confirm_id>``
        и резолвится через ``tools.slash_confirm.resolve``.
        """
        reply_to = (metadata or {}).get("reply_to")
        text = message if len(message) <= MAX_MESSAGE_LENGTH else message[: MAX_MESSAGE_LENGTH - 3] + "..."
        buttons: List[List[Dict[str, str]]] = [
            [
                {"type": "callback", "text": "✅ Один раз", "payload": f"sc:once:{confirm_id}"},
                {"type": "callback", "text": "🔒 Всегда", "payload": f"sc:always:{confirm_id}"},
            ],
            [
                {"type": "callback", "text": "❌ Отмена", "payload": f"sc:cancel:{confirm_id}"},
            ],
        ]
        self._slash_confirm_state[confirm_id] = session_key
        return await self._send_inline_buttons(chat_id, text, buttons, reply_to)

    async def _resolve_button_payload(self, payload: str, chat_id: str) -> bool:
        """Обработать нажатие инлайновой кнопки, если это clarify/confirm.

        Возвращает True, если payload распознан и обработан.
        """
        if payload.startswith("cl:"):
            parts = payload.split(":", 2)
            if len(parts) != 3:
                return False
            clarify_id, idx = parts[1], parts[2]
            session_key = self._clarify_state.get(clarify_id)
            if not session_key:
                logger.info("clarify %s уже неактуален", clarify_id)
                return True
            try:
                from tools import clarify_gateway as _cg
                if idx == "other":
                    _cg.mark_awaiting_text(clarify_id)
                    await self.send(chat_id, "✏️ Напишите свой вариант ответа.")
                    return True
                try:
                    num = int(idx)
                except (ValueError, TypeError):
                    return True
                # Текст варианта берём из зарегистрированной записи clarify.
                resolved_text: Optional[str] = None
                try:
                    from tools.clarify_gateway import _entries as _clarify_entries
                    entry = _clarify_entries.get(clarify_id)
                    if entry and entry.choices and 0 <= num < len(entry.choices):
                        resolved_text = entry.choices[num]
                except Exception:
                    resolved_text = None
                if resolved_text is None:
                    resolved_text = f"choice {num + 1}"
                self._clarify_state.pop(clarify_id, None)
                _cg.resolve_gateway_clarify(clarify_id, resolved_text)
                await self.send(chat_id, f"✅ Выбрано: {resolved_text}")
            except Exception as e:
                logger.error("clarify resolve failed: %s", e, exc_info=True)
            return True

        if payload.startswith("sc:"):
            parts = payload.split(":", 2)
            if len(parts) != 3:
                return False
            choice, confirm_id = parts[1], parts[2]
            session_key = self._slash_confirm_state.pop(confirm_id, None)
            if not session_key:
                return True
            labels = {"once": "✅ Подтверждено один раз",
                      "always": "🔒 Всегда подтверждено",
                      "cancel": "❌ Отменено"}
            try:
                from tools import slash_confirm as _sc
                result_text = await _sc.resolve(session_key, confirm_id, choice)
                await self.send(chat_id, labels.get(choice, "Готово"))
                if result_text:
                    await self.send(chat_id, result_text)
            except Exception as e:
                logger.error("slash-confirm resolve failed: %s", e, exc_info=True)
            return True

        return False

    async def _send_attachment(
        self,
        chat_id: str,
        att_type: str,
        token: str,
        caption: str = "",
        reply_to: Optional[str] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a previously-uploaded attachment (image/file) to MAX."""
        if not self._client:
            return SendResult(success=False, error="Not connected")
        payload: Dict[str, Any] = {
            "attachments": [
                {"type": att_type, "payload": {"token": token, **(extra_payload or {})}}
            ]
        }
        if caption:
            text = caption
            if len(text) > MAX_MESSAGE_LENGTH:
                text = text[: MAX_MESSAGE_LENGTH - 3] + "..."
            payload["text"] = text
            if has_markdown(caption):
                payload["format"] = "markdown"
        if reply_to:
            payload["reply_to"] = reply_to
        # MAX API: личные сообщения адресуются по user_id, группы — по chat_id
        try:
            cid = int(chat_id)
        except (ValueError, TypeError):
            return SendResult(success=False, error="Bad chat_id")
        query = f"user_id={cid}" if cid > 0 else f"chat_id={cid}"
        try:
            result = await self._client._request("POST", f"/messages?{query}", data=payload)
            mid = ((result or {}).get("message") or {}).get("body", {}).get("mid", "")
            if chat_id:
                self._last_message_ids[chat_id] = mid
            logger.info("MAX attachment sent: type=%s mid=%s", att_type, mid)
            return SendResult(success=True, message_id=mid)
        except Exception as e:
            logger.error("MAX attachment send error: %s", e)
            return SendResult(success=False, error=str(e))

    async def send_image(
        self,
        chat_id: str,
        image_path: str,
        caption: str = "",
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SendResult:
        """Send a local image file to MAX as a native photo attachment."""
        try:
            if not self._client:
                return SendResult(success=False, error="Not connected")
            # Статус «отправляет фото…», пока идёт загрузка
            await self.send_action(chat_id, "sending_photo")
            with open(image_path, "rb") as _f:
                _data = _f.read()
            _name = os.path.basename(image_path)
            _lower = _name.lower()
            if _lower.endswith(".png"):
                _ctype = "image/png"
            elif _lower.endswith(".webp"):
                _ctype = "image/webp"
            elif _lower.endswith(".gif"):
                _ctype = "image/gif"
            else:
                _ctype = "image/jpeg"
            image_token = await self._client.upload_image(_data, _name, _ctype)
            if not image_token:
                return SendResult(success=False, error="Failed to upload image")
            return await self._send_attachment(chat_id, "image", image_token, caption, reply_to)
        except Exception as e:
            logger.error("send_image error: %s", e)
            return SendResult(success=False, error=str(e))

    async def send_image_file(
        self,
        chat_id: str,
        image_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        """Gateway hook for native image attachments (MEDIA: / cron delivery)."""
        return await self.send_image(chat_id, image_path, caption or "", reply_to, metadata)

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        """Send a local file to MAX as a native document attachment."""
        try:
            if not self._client:
                return SendResult(success=False, error="Not connected")
            # Статус «отправляет файл…», пока идёт загрузка
            await self.send_action(chat_id, "sending_file")
            with open(file_path, "rb") as _f:
                _data = _f.read()
            _name = os.path.basename(file_path)
            _token = await self._client.upload_file(
                _data, _name, "application/octet-stream"
            )
            if hasattr(_token, "token"):
                _token = getattr(_token, "token", "") or _token
            if not _token:
                return SendResult(success=False, error="Failed to upload file")
            return await self._send_attachment(
                chat_id, "file", _token, caption or "", reply_to,
                extra_payload={"name": _name},
            )
        except Exception as e:
            logger.error("send_document error: %s", e)
            return SendResult(success=False, error=str(e))

    async def health_check(self) -> bool:
        """Health check: check MAX connection."""
        if not self._client:
            return False
        try:
            bot_info = await self._client.get_bot_info()
            return bool(bot_info)
        except Exception:
            return False
    async def _poll_inbox(self):
        """Legacy polling — delegated to _polling_loop."""
        pass


def register(ctx):
    """Register the MAX platform adapter with Hermes gateway."""
    def _check():
        try:
            import aiohttp  # noqa: F401
            token = os.environ.get("MAX_BOT_TOKEN", "")
            return bool(token)
        except ImportError:
            return False

    ctx.register_platform(
        name="max",
        label="MAX",
        adapter_factory=lambda cfg: MaxAdapter(cfg),
        check_fn=_check,
        emoji="💬",
        setup_fn=None,
    )
    logger.info("MAX platform adapter registered")
