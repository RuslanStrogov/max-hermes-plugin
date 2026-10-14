"""Message format converter between MAX API and internal message format.

Converts MAX Bot API webhook payloads to a normalized internal format
suitable for processing by Hermes Agent or any other consumer.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from max_shared.constants import GROUP_CHAT_TYPES
from max_shared.markdown import has_markdown
from max_shared.models import MAXUpdate, MAXMessage, UpdateType

logger = logging.getLogger(__name__)


class MessageConverter:
    """Converts between MAX API format and internal message format.

    The internal format is a plain dict with these fields:
    - message: str — text content (may include attachment placeholders)
    - chat_id: str
    - user_id: str
    - user_name: str
    - platform: str — always "max"
    - reply_to: Optional[str] — message ID being replied to
    - attachments: List[Dict] — attachment metadata (url, token, type)
    - raw_update: Dict — original update metadata
    """

    # ── MAX to Internal ────────────────────────────────────────────────────

    @staticmethod
    def max_update_to_message(update: MAXUpdate) -> Optional[Dict[str, Any]]:
        """Convert MAX Update to internal message payload.

        Returns None if the update type is not supported / should be silently ignored.
        """
        handlers = {
            UpdateType.MESSAGE_CREATED: MessageConverter._message_created,
            UpdateType.MESSAGE_EDITED: MessageConverter._message_edited,
            UpdateType.MESSAGE_REMOVED: MessageConverter._message_removed,
            UpdateType.MESSAGE_CALLBACK: MessageConverter._callback,
            UpdateType.BOT_STARTED: MessageConverter._bot_started,
            UpdateType.BOT_ADDED: MessageConverter._bot_added,
            UpdateType.BOT_REMOVED: MessageConverter._bot_removed,
            UpdateType.CHAT_CREATED: MessageConverter._chat_created,
            UpdateType.USER_ADDED: MessageConverter._user_added,
            UpdateType.USER_REMOVED: MessageConverter._user_removed,
            UpdateType.CHAT_TITLE_CHANGED: MessageConverter._chat_title_changed,
        }

        handler = handlers.get(update.update_type)
        if handler is None:
            logger.debug("Unsupported update type: %s", update.update_type)
            return None

        # For message-based events, ensure message exists
        if update.update_type in (
            UpdateType.MESSAGE_CREATED,
            UpdateType.MESSAGE_EDITED,
            UpdateType.MESSAGE_REMOVED,
        ):
            if update.message is None:
                return None

        return handler(update)

    @staticmethod
    def _message_created(update: MAXUpdate) -> Dict[str, Any]:
        """Convert message_created update."""
        message = update.message
        if message is None:
            return MessageConverter._empty_payload("message_created")

        text = message.body.text or ""

        # Build attachment info
        attachments_info = []
        if message.body.attachments:
            for att in message.body.attachments:
                attachments_info.append({
                    "type": att.type,
                    "url": att.payload.url,
                    "token": att.payload.token,
                    "metadata": att.payload.metadata,
                })

            # Append attachment descriptions to text
            attachment_text = MessageConverter._format_attachments(attachments_info)
            if attachment_text:
                text = f"{text}\n{attachment_text}" if text else attachment_text

        return {
            "message": text,
            "chat_id": str(message.recipient.chat_id),
            "user_id": str(message.sender.user_id),
            "user_name": message.sender.display_name,
            "platform": "max",
            "reply_to": message.body.mid,
            "attachments": attachments_info,
            "raw_update": {
                "update_type": "message_created",
                "message_id": message.body.mid,
                "timestamp": message.timestamp,
            },
        }

    @staticmethod
    def _callback(update: MAXUpdate) -> Dict[str, Any]:
        """Convert callback (button press)."""
        callback_data = update.callback or {}
        message = update.message

        button_text = callback_data.get("text", "")
        payload = callback_data.get("payload", "")
        text = f"[Кнопка: {button_text}]"
        if payload:
            text += f"\nPayload: {payload}"

        if message:
            return {
                "message": text,
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
                "reply_to": message.body.mid,
                "raw_update": {
                    "update_type": "message_callback",
                    "callback_id": callback_data.get("id"),
                    "payload": payload,
                },
            }
        return {
            "message": text,
            "chat_id": str(callback_data.get("chat_id", "")),
            "user_id": str(callback_data.get("user_id", "")),
            "user_name": callback_data.get("user_name", "Unknown"),
            "platform": "max",
            "raw_update": {
                "update_type": "message_callback",
                "callback_id": callback_data.get("id"),
                "payload": payload,
            },
        }

    @staticmethod
    def _bot_started(update: MAXUpdate) -> Dict[str, Any]:
        """Convert bot_started event."""
        message = update.message
        if message:
            return {
                "message": "/start",
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
            }
        return MessageConverter._empty_payload("bot_started", message_text="/start")

    @staticmethod
    def _message_edited(update: MAXUpdate) -> Dict[str, Any]:
        """Convert message_edited update."""
        message = update.message
        if message is None:
            return MessageConverter._empty_payload("message_edited")
        text = message.body.text or ""
        return {
            "message": f"[Отредактировано] {text}",
            "chat_id": str(message.recipient.chat_id),
            "user_id": str(message.sender.user_id),
            "user_name": message.sender.display_name,
            "platform": "max",
            "reply_to": message.body.mid,
            "raw_update": {
                "update_type": "message_edited",
                "message_id": message.body.mid,
                "timestamp": message.timestamp,
            },
        }

    @staticmethod
    def _message_removed(update: MAXUpdate) -> Dict[str, Any]:
        """Convert message_removed update."""
        message = update.message
        if message is None:
            return MessageConverter._empty_payload("message_removed")
        return {
            "message": "[Сообщение удалено]",
            "chat_id": str(message.recipient.chat_id),
            "user_id": str(message.sender.user_id),
            "user_name": message.sender.display_name,
            "platform": "max",
            "raw_update": {
                "update_type": "message_removed",
                "message_id": message.body.mid,
                "timestamp": message.timestamp,
            },
        }

    @staticmethod
    def _bot_added(update: MAXUpdate) -> Dict[str, Any]:
        """Convert bot_added event."""
        message = update.message
        if message:
            return {
                "message": "[Бот добавлен в чат]",
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
                "raw_update": {
                    "update_type": "bot_added",
                    "timestamp": update.timestamp,
                },
            }
        return MessageConverter._empty_payload("bot_added", message_text="[Бот добавлен в чат]")

    @staticmethod
    def _bot_removed(update: MAXUpdate) -> Dict[str, Any]:
        """Convert bot_removed event."""
        message = update.message
        if message:
            return {
                "message": "[Бот удалён из чата]",
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
                "raw_update": {
                    "update_type": "bot_removed",
                    "timestamp": update.timestamp,
                },
            }
        return MessageConverter._empty_payload("bot_removed", message_text="[Бот удалён из чата]")

    @staticmethod
    def _chat_created(update: MAXUpdate) -> Dict[str, Any]:
        """Convert chat_created event."""
        message = update.message
        if message:
            return {
                "message": "[Чат создан]",
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
                "raw_update": {
                    "update_type": "chat_created",
                    "timestamp": update.timestamp,
                },
            }
        return MessageConverter._empty_payload("chat_created", message_text="[Чат создан]")

    @staticmethod
    def _user_added(update: MAXUpdate) -> Dict[str, Any]:
        """Convert user_added event."""
        message = update.message
        if message:
            return {
                "message": f"[Пользователь добавлен в чат: {message.sender.display_name}]",
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
                "raw_update": {
                    "update_type": "user_added",
                    "timestamp": update.timestamp,
                },
            }
        return MessageConverter._empty_payload("user_added", message_text="[Пользователь добавлен в чат]")

    @staticmethod
    def _user_removed(update: MAXUpdate) -> Dict[str, Any]:
        """Convert user_removed event."""
        message = update.message
        if message:
            return {
                "message": f"[Пользователь покинул чат: {message.sender.display_name}]",
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
                "raw_update": {
                    "update_type": "user_removed",
                    "timestamp": update.timestamp,
                },
            }
        return MessageConverter._empty_payload("user_removed", message_text="[Пользователь покинул чат]")

    @staticmethod
    def _chat_title_changed(update: MAXUpdate) -> Dict[str, Any]:
        """Convert chat_title_changed event."""
        message = update.message
        if message:
            return {
                "message": "[Название чата изменено]",
                "chat_id": str(message.recipient.chat_id),
                "user_id": str(message.sender.user_id),
                "user_name": message.sender.display_name,
                "platform": "max",
                "raw_update": {
                    "update_type": "chat_title_changed",
                    "timestamp": update.timestamp,
                },
            }
        return MessageConverter._empty_payload("chat_title_changed", message_text="[Название чата изменено]")

    # ── Internal to MAX ────────────────────────────────────────────────────

    @staticmethod
    def response_to_max_message(
        response: Dict[str, Any],
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Convert internal response to MAX API message format.

        For dialogs (DM): pass user_id — takes priority over chat_id.
        For group chats: pass chat_id only.
        """
        text = response.get("message", response.get("text", ""))
        if not text:
            text = "..."

        payload: Dict[str, Any] = {"text": text}

        if user_id is not None and user_id > 0:
            payload["user_id"] = user_id
        elif chat_id is not None and chat_id > 0:
            payload["chat_id"] = chat_id
        else:
            logger.warning("Neither user_id nor chat_id available for response")

        if has_markdown(text):
            payload["format"] = "markdown"

        return payload

    # ── Utility ────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_payload(
        update_type: str,
        message_text: str = "",
    ) -> Dict[str, Any]:
        """Build an empty payload for events without message data."""
        return {
            "message": message_text,
            "chat_id": "unknown",
            "user_id": "unknown",
            "user_name": "Unknown",
            "platform": "max",
            "raw_update": {"update_type": update_type},
        }

    @staticmethod
    def _format_attachments(attachments: List[Dict[str, Any]]) -> str:
        """Format MAX attachments for message text with URLs."""
        parts = []
        for att in attachments:
            att_type = att.get("type", "")
            url = att.get("url", "")

            if att_type == "image":
                label = "🖼 [Изображение]"
            elif att_type == "video":
                label = "🎬 [Видео]"
            elif att_type in ("audio", "voice"):
                label = "🎤 [Голосовое сообщение]"
            elif att_type == "file":
                name = att.get("name", "Файл")
                label = f"📎 [Файл: {name}]"
            elif att_type == "contact":
                label = "[Контакт]"
            elif att_type == "inline_keyboard":
                continue
            else:
                label = f"[{att_type}]"

            if url:
                label += f"\nURL: {url}"
            parts.append(label)

        return "\n".join(parts)

    @staticmethod
    def parse_webhook_payload(raw_body: bytes) -> MAXUpdate:
        """Parse raw webhook payload from MAX into MAXUpdate."""
        data = json.loads(raw_body)
        return MAXUpdate(**data)

    @staticmethod
    def build_inline_keyboard(
        buttons: List[List[Dict[str, str]]],
    ) -> Dict[str, Any]:
        """Build MAX inline keyboard attachment.

        Args:
            buttons: List of rows, each row is a list of button dicts.
                    Each button: {"type": "callback", "text": "...", "payload": "..."}

        Returns:
            MAX API attachment dict.
        """
        return {
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        }

    @staticmethod
    def determine_reply_target(
        recipient: Any,
        sender: Any,
    ) -> tuple[Optional[int], Optional[int]]:
        """Determine chat_id/user_id for sending a reply.

        Returns:
            Tuple of (chat_id, user_id). One will be None.
        """
        chat_type = getattr(recipient, 'effective_chat_type',
                           getattr(recipient, 'chat_type', 'dialog'))
        is_group = chat_type in GROUP_CHAT_TYPES

        if is_group:
            return recipient.chat_id, None
        else:
            return None, sender.user_id
