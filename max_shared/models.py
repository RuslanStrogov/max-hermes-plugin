"""Pydantic models for MAX Bot API data structures."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── MAX Bot API Models ─────────────────────────────────────────────────────


class UpdateType(str, Enum):
    """MAX API update types."""
    MESSAGE_CREATED = "message_created"
    MESSAGE_EDITED = "message_edited"
    MESSAGE_REMOVED = "message_removed"
    MESSAGE_CALLBACK = "message_callback"
    BOT_ADDED = "bot_added"
    BOT_REMOVED = "bot_removed"
    BOT_STARTED = "bot_started"
    CHAT_CREATED = "chat_created"
    USER_ADDED = "user_added"
    USER_REMOVED = "user_removed"
    CHAT_TITLE_CHANGED = "chat_title_changed"


class MAXUser(BaseModel):
    """User info from MAX API."""
    user_id: int
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    username: Optional[str] = None
    is_bot: bool = False
    last_activity_time: Optional[int] = None

    model_config = ConfigDict(extra="allow")

    @property
    def display_name(self) -> str:
        """Get user display name (fallback to first_name + last_name)."""
        if self.name:
            return self.name
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or "Unknown"


class MAXRecipient(BaseModel):
    """Message recipient."""
    chat_id: int
    chat_type: str = "dialog"
    user_id: Optional[int] = None
    type: str = "dialog"

    model_config = ConfigDict(extra="allow")

    @property
    def is_group(self) -> bool:
        """Check if this is a group chat."""
        return self.chat_type in ("group", "channel", "supergroup")

    @property
    def effective_chat_type(self) -> str:
        """Get chat type (fallback to 'type' field)."""
        return self.chat_type or self.type or "dialog"


class MAXAttachmentPayload(BaseModel):
    """Attachment payload — contains URL and access token."""
    url: Optional[str] = None
    token: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    def get_effective_token(self) -> Optional[str]:
        return self.token


class MAXAttachment(BaseModel):
    """Single attachment from MAX message."""
    type: str = ""
    payload: MAXAttachmentPayload = Field(default_factory=MAXAttachmentPayload)

    model_config = ConfigDict(extra="allow")

    @property
    def is_media(self) -> bool:
        return self.type in ("image", "video", "audio", "voice")

    @property
    def is_file(self) -> bool:
        return self.type == "file"

    @property
    def is_image(self) -> bool:
        return self.type == "image"

    @property
    def is_video(self) -> bool:
        return self.type == "video"

    @property
    def is_audio(self) -> bool:
        return self.type in ("audio", "voice")


class MAXMessageBody(BaseModel):
    """Message body."""
    text: Optional[str] = None
    mid: Optional[str] = None
    seq: Optional[int] = None
    attachments: List[MAXAttachment] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class MAXMessage(BaseModel):
    """Message object from MAX API."""
    sender: MAXUser
    recipient: MAXRecipient
    body: MAXMessageBody
    timestamp: int

    model_config = ConfigDict(extra="allow")


class MAXUpdate(BaseModel):
    """Incoming update from MAX API."""
    update_type: UpdateType
    message: Optional[MAXMessage] = None
    callback: Optional[Dict[str, Any]] = None
    timestamp: int
    user_locale: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class SendMessageResponse(BaseModel):
    """Response from POST /messages."""
    message_id: Optional[str] = None
    ok: bool = True
    error: Optional[str] = None


class SubscriptionResponse(BaseModel):
    """Response from POST /subscriptions."""
    id: Optional[str] = None
    url: Optional[str] = None
    ok: bool = True


# ─── Content Models ─────────────────────────────────────────────────────────


class ContentType(str, Enum):
    """Types of downloadable content from MAX attachments."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    VOICE = "voice"
    CONTACT = "contact"
    LOCATION = "location"
    STICKER = "sticker"


class ContentItem(BaseModel):
    """A single content item downloaded from MAX attachment.

    Passed to Hermes agent so it can read/process the actual file.
    """
    content_type: ContentType
    local_path: str
    original_url: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class OutgoingAttachment(BaseModel):
    """Attachment for sending messages to MAX."""
    type: str
    attachment_id: Optional[str] = None
    url: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class UploadResponse(BaseModel):
    """Response from POST /uploads."""
    attachment_id: Optional[str] = None
    url: Optional[str] = None
    ok: bool = True
    error: Optional[str] = None
