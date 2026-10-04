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
    "/start": "👋 Привет! Я бот Hermes Agent на платформе MAX. Готов помогать!",
    "start": "👋 Привет! Я бот Hermes Agent на платформе MAX. Готов помогать!",
    "/help": (
        "📚 Команды бота:\n"
        "/start — начать диалог\n"
        "/help — эта справка"
    ),
    "help": (
        "📚 Команды бота:\n"
        "/start — начать диалог\n"
        "/help — эта справка"
    ),
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
            self._bot_user_id = bot_info.get("user_id", 0)
            logger.info("Connected to MAX as: %s (user_id=%s)", bot_info.get("name", "unknown"), self._bot_user_id)

            # Register bot commands (menu button)
            try:
                cmds = DEFAULT_COMMANDS.copy()
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
        # Не отвечаем на свои же сообщения
        bot_self_id = int(os.environ.get("MAX_BOT_SELF_ID", "0")) or \
            getattr(self, '_bot_user_id', 0)
        if bot_self_id and user_id == bot_self_id:
            logger.info("Self-msg ignored: user_id=%s == bot_self_id", user_id)
            return False
        # В личных чатах (dialog) отвечаем всегда
        if chat_type in ("dialog",):
            return True
        # Всегда отвечаем разрешённым пользователям
        if self._allowed_users and user_id in self._allowed_users:
            return True
        # Отвечаем если упомянут бот (@username)
        bot_username = os.environ.get("MAX_BOT_USERNAME", "").lower()
        if bot_username and f"@{bot_username}" in text.lower():
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

        # Отправляем индикатор «Печатает...» перед запуском агента
        if self._client:
            logger.info("SENDING typing to chat_id=%s", str(chat_id))
            await self.send_typing(str(chat_id))

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
        # Запоминаем chat_id для прямого пуллинга сообщений
        self._last_message_ids[str(chat_id)] = body.get("mid", "")

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

        # Отправляем индикатор «Печатает...» перед запуском агента
        if self._client:
            await self.send_typing(str(chat_id))

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

    async def send_typing(self, chat_id: str):
        """Send typing indicator."""
        logger.info("send_typing to chat_id=%s", chat_id)
        await self._client.send_chat_action(chat_id=int(chat_id), action="typing_on")

    async def send_image(
        self,
        chat_id: str,
        image_path: str,
        caption: str = "",
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SendResult:
        """Send an image to MAX."""
        try:
            if not self._client:
                return SendResult(success=False, error="Not connected")
            image_token = await self._client.upload_image(image_path)
            if not image_token:
                return SendResult(success=False, error="Failed to upload image")
            result = await self._client.send_message(
                chat_id=int(chat_id),
                text=caption or "",
                attachments=[{
                    "type": "image",
                    "payload": {"token": image_token},
                }],
                reply_to=reply_to,
            )
            return SendResult(
                success=True,
                message_id=result.message_id,
            )
        except Exception as e:
            logger.error("send_image error: %s", e)
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
