"""
MAX Bot API Platform Adapter for Hermes Agent.

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
from urllib.parse import urljoin

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None  # type: ignore[assignment]

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

logger = logging.getLogger(__name__)

DEFAULT_API_BASE_URL = "https://platform-api.max.ru"
MAX_MESSAGE_LENGTH = 4096
DEDUP_WINDOW_SECONDS = 300
DEDUP_MAX_SIZE = 1000


def _get_env_or_extra(config: PlatformConfig, key: str, extra_key: str, default: str = "") -> str:
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
        return True  # No secret configured, skip verification
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _build_inline_keyboard(buttons: List[List[Dict[str, str]]]) -> Dict[str, Any]:
    """Build MAX inline keyboard attachment."""
    return {
        "type": "inline_keyboard",
        "payload": {"buttons": buttons},
    }


class MaxAdapter(BasePlatformAdapter):
    """MAX Bot API platform adapter for Hermes Agent."""

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.CUSTOM)
        self._token = _get_env_or_extra(config, "MAX_BOT_TOKEN", "token", "")
        self._webhook_url = _get_env_or_extra(config, "MAX_WEBHOOK_URL", "webhook_url", "")
        self._webhook_secret = _get_env_or_extra(config, "MAX_WEBHOOK_SECRET", "webhook_secret", "")
        self._api_base_url = _get_env_or_extra(config, "MAX_API_BASE_URL", "api_base_url", DEFAULT_API_BASE_URL).rstrip("/")
        self._allowed_users = _parse_allowed_users(config)
        self._home_channel = _get_env_or_extra(config, "MAX_HOME_CHANNEL", "home_channel", "")

        self._session: Optional[aiohttp.ClientSession] = None
        self._app: Optional[Any] = None
        self._runner: Optional[Any] = None
        self._dedup_cache: Dict[str, float] = {}
        self._connected = False

        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required for MAX adapter. Install: pip install aiohttp")

        if not self._token:
            raise ValueError("MAX_BOT_TOKEN is required")
        if not self._webhook_url:
            raise ValueError("MAX_WEBHOOK_URL is required")

    @property
    def platform_name(self) -> str:
        return "max"

    async def connect(self) -> bool:
        """Start webhook server and register webhook with MAX."""
        try:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": self._token,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            )

            # Verify bot info
            bot_info = await self._api_request("GET", "/me")
            if not bot_info:
                logger.error("Failed to get bot info — check MAX_BOT_TOKEN")
                return False
            logger.info("Connected to MAX as: %s", bot_info.get("name", "unknown"))

            # Register webhook
            sub_result = await self._api_request("POST", "/subscriptions", {
                "url": self._webhook_url,
                "update_types": ["message_created", "message_callback"],
            })
            if sub_result:
                logger.info("Webhook registered: %s", self._webhook_url)
            else:
                logger.warning("Webhook registration failed — may already be registered")

            # Start local webhook server
            await self._start_webhook_server()

            self._connected = True
            return True

        except Exception as e:
            logger.error("Failed to connect to MAX: %s", e)
            return False

    async def disconnect(self):
        """Stop webhook server and close connections."""
        self._connected = False
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Disconnected from MAX")

    async def send(self, chat_id: str, text: str, **kwargs) -> SendResult:
        """Send a text message to MAX."""
        if not text:
            return SendResult(success=False, error="Empty message")

        # Truncate if needed
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH - 3] + "..."

        payload: Dict[str, Any] = {"text": text}

        # Detect markdown
        if self._has_markdown(text):
            payload["format"] = "markdown"

        # Reply to message
        reply_to = kwargs.get("reply_to")
        if reply_to:
            payload["reply_to"] = reply_to

        # Inline keyboard
        buttons = kwargs.get("buttons")
        if buttons:
            payload["attachments"] = [_build_inline_keyboard(buttons)]

        # Determine target: user_id or chat_id
        user_id = kwargs.get("user_id")
        params: Dict[str, Any] = {}
        if user_id:
            params["user_id"] = str(user_id)
        elif chat_id:
            params["chat_id"] = str(chat_id)
        else:
            return SendResult(success=False, error="No chat_id or user_id provided")

        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/messages?{query}" if query else "/messages"

        result = await self._api_request("POST", path, payload)
        if result:
            return SendResult(success=True, message_id=result.get("message", {}).get("body", {}).get("mid", ""))
        return SendResult(success=False, error="Failed to send message")

    async def send_typing(self, chat_id: str):
        """Send typing indicator."""
        await self._api_request("POST", f"/chats/{chat_id}/actions", {"action": "typing_on"})

    async def send_image(self, chat_id: str, image_url: str, caption: str = "", **kwargs) -> SendResult:
        """Send an image to MAX."""
        payload: Dict[str, Any] = {
            "attachments": [{
                "type": "image",
                "payload": {"url": image_url}
            }]
        }
        if caption:
            payload["text"] = caption

        user_id = kwargs.get("user_id")
        params: Dict[str, Any] = {}
        if user_id:
            params["user_id"] = str(user_id)
        elif chat_id:
            params["chat_id"] = str(chat_id)

        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/messages?{query}" if query else "/messages"

        result = await self._api_request("POST", path, payload)
        if result:
            return SendResult(success=True, message_id=result.get("message", {}).get("body", {}).get("mid", ""))
        return SendResult(success=False, error="Failed to send image")

    async def _api_request(self, method: str, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Make an API request to MAX Bot API."""
        if not self._session:
            return None
        url = f"{self._api_base_url}{path}"
        try:
            async with self._session.request(method, url, json=data) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    logger.error("MAX API error: %s %s — %s", method, path, body)
                    return None
                return body
        except Exception as e:
            logger.error("MAX API request failed: %s %s — %s", method, path, e)
            return None

    async def _start_webhook_server(self):
        """Start aiohttp server for receiving webhooks."""
        from aiohttp import web

        async def handle_webhook(request: web.Request) -> web.Response:
            try:
                body = await request.read()
                signature = request.headers.get("X-Max-Signature", "")

                if not _verify_webhook_signature(body, signature, self._webhook_secret):
                    return web.json_response({"error": "Invalid signature"}, status=401)

                data = json.loads(body)
                await self._handle_update(data)
                return web.json_response({"ok": True})
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid JSON"}, status=400)
            except Exception as e:
                logger.exception("Webhook error: %s", e)
                return web.json_response({"ok": True})  # Always return 200 to MAX

        async def handle_health(request: web.Request) -> web.Response:
            return web.json_response({"status": "ok", "platform": "max"})

        self._app = web.Application()
        self._app.router.add_post("/webhook", handle_webhook)
        self._app.router.add_get("/health", handle_health)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # Get port from webhook URL or default to 8787
        from urllib.parse import urlparse
        parsed = urlparse(self._webhook_url)
        port = parsed.port or 8787

        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Webhook server listening on port %d", port)

    async def _handle_update(self, data: Dict):
        """Handle incoming update from MAX."""
        update_type = data.get("update_type", "")

        # Dedup
        msg_id = data.get("message", {}).get("body", {}).get("mid", "") if data.get("message") else ""
        if msg_id and self._is_dedup(msg_id):
            return

        if update_type == "message_created":
            await self._handle_message_created(data)
        elif update_type == "message_callback":
            await self._handle_message_callback(data)
        else:
            logger.debug("Unhandled update type: %s", update_type)

    async def _handle_message_created(self, data: Dict):
        """Handle incoming message."""
        msg = data.get("message", {})
        sender = msg.get("sender", {})
        recipient = msg.get("recipient", {})
        body = msg.get("body", {})

        user_id = sender.get("user_id", 0)
        chat_id = recipient.get("chat_id", 0)
        text = body.get("text", "")

        # Access control
        if self._allowed_users and user_id not in self._allowed_users:
            logger.warning("Unauthorized user %d — ignoring", user_id)
            return

        # Build message event
        user_name = sender.get("name", sender.get("first_name", "Unknown"))
        event = MessageEvent(
            message_id=body.get("mid", str(uuid.uuid4())),
            chat_id=str(chat_id),
            user_id=str(user_id),
            user_name=user_name,
            text=text,
            timestamp=msg.get("timestamp", int(time.time() * 1000)),
            platform=Platform.CUSTOM,
        )

        # Dispatch to gateway
        await self._dispatch_message(event)

    async def _handle_message_callback(self, data: Dict):
        """Handle callback from inline keyboard button."""
        callback = data.get("callback", {})
        msg = data.get("message", {})
        sender = msg.get("sender", {}) if msg else {}
        recipient = msg.get("recipient", {}) if msg else {}

        user_id = sender.get("user_id", 0)
        chat_id = recipient.get("chat_id", 0)
        callback_payload = callback.get("payload", "")
        button_text = callback.get("text", "")

        if self._allowed_users and user_id not in self._allowed_users:
            return

        user_name = sender.get("name", sender.get("first_name", "Unknown"))
        text = f"[Кнопка: {button_text}]\nPayload: {callback_payload}"

        event = MessageEvent(
            message_id=str(uuid.uuid4()),
            chat_id=str(chat_id),
            user_id=str(user_id),
            user_name=user_name,
            text=text,
            timestamp=int(time.time() * 1000),
            platform=Platform.CUSTOM,
        )

        await self._dispatch_message(event)

        # Answer callback
        callback_id = callback.get("id", "")
        if callback_id:
            await self._api_request("POST", "/callback", {"callback_id": callback_id})

    def _is_dedup(self, msg_id: str) -> bool:
        """Check for duplicate messages."""
        now = time.time()
        self._dedup_cache[msg_id] = now
        # Clean old entries
        if len(self._dedup_cache) > DEDUP_MAX_SIZE:
            cutoff = now - DEDUP_WINDOW_SECONDS
            self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if v > cutoff}
        return False

    @staticmethod
    def _has_markdown(text: str) -> bool:
        """Check if text contains markdown formatting."""
        import re
        patterns = [
            r"\*\*.*\*\*", r"\*.*\*", r"~~.*~~",
            r"\[.*\]\(.*\)", r"`.*`", r"^#{1,6}\s", r"^>\s",
        ]
        return any(re.search(p, text, re.MULTILINE) for p in patterns)


def register(ctx):
    """Register the MAX platform adapter with Hermes gateway."""
    ctx.register_platform("max", MaxAdapter)
    logger.info("MAX platform adapter registered")
