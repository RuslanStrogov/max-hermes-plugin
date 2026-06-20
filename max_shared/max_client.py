"""Async HTTP client for MAX Bot API.

Combines the HTTP layer from max-hermes (aiohttp-based) with features
from max-hermes-plugin (file upload, download).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from max_shared.constants import DEFAULT_API_BASE_URL, DEFAULT_TIMEOUT_SECONDS
from max_shared.models import (
    SendMessageResponse,
    SubscriptionResponse,
    UploadResponse,
)

logger = logging.getLogger(__name__)


class MAXApiError(Exception):
    """MAX API error."""

    def __init__(self, code: str, message: str, status_code: int = 0):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{code}] {message} (HTTP {status_code})")


class MAXClient:
    """Async HTTP client for MAX Bot API.

    Features:
    - Message send/edit/delete
    - Webhook subscription management
    - Long polling fallback
    - File upload (image, audio, generic file)
    - Attachment download
    - Chat actions (typing indicator)
    - Callback answers
    """

    def __init__(
        self,
        token: str,
        base_url: str = DEFAULT_API_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": self._token,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a JSON API request."""
        session = await self._get_session()
        url = f"{self._base_url}{path}"
        logger.debug("MAX API %s %s", method, url)

        try:
            async with session.request(method, url, json=data) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    code = body.get("code", "unknown")
                    message = body.get("message", "Unknown error")
                    logger.error(
                        "MAX API error: %s %s (HTTP %d)", code, message, resp.status
                    )
                    raise MAXApiError(code, message, resp.status)
                return body
        except aiohttp.ClientError as e:
            logger.error("MAX API connection error: %s", e)
            raise

    async def _upload_request(
        self,
        path: str,
        data: aiohttp.FormData,
    ) -> Dict[str, Any]:
        """Make a multipart/form-data upload request."""
        session = await self._get_session()
        url = f"{self._base_url}{path}"

        async with session.post(url, data=data) as resp:
            body = await resp.json(content_type=None)
            if resp.status >= 400:
                code = body.get("code", "unknown")
                message = body.get("message", "Unknown error")
                raise MAXApiError(code, message, resp.status)
            return body

    # ── Bot info ────────────────────────────────────────────────────────────

    async def get_bot_info(self) -> Dict[str, Any]:
        """GET /me — get bot info."""
        return await self._request("GET", "/me")

    # ── Messages ────────────────────────────────────────────────────────────

    async def send_message(
        self,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        text: str = "",
        format: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        reply_to: Optional[str] = None,
    ) -> SendMessageResponse:
        """POST /messages — send a message.

        For dialogs (DM): pass user_id.
        For group chats: pass chat_id.
        """
        logger.info(
            "send_message: chat_id=%s, user_id=%s, text_len=%d",
            chat_id,
            user_id,
            len(text),
        )

        params: Dict[str, str] = {}
        if chat_id is not None:
            params["chat_id"] = str(chat_id)
        if user_id is not None:
            params["user_id"] = str(user_id)

        payload: Dict[str, Any] = {}
        if text:
            payload["text"] = text
        if format:
            payload["format"] = format
        if attachments:
            payload["attachments"] = attachments
        if reply_to:
            payload["reply_to"] = reply_to

        if not params:
            raise MAXApiError(
                "validation",
                "Either chat_id or user_id must be provided",
                400,
            )

        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/messages?{query}" if query else "/messages"

        body = await self._request("POST", path, data=payload)
        return SendMessageResponse(
            message_id=body.get("message_id"),
            ok=True,
        )

    async def edit_message(
        self,
        message_id: int,
        text: str,
        format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """PUT /messages/{messageId} — edit a message."""
        payload: Dict[str, Any] = {"text": text}
        if format:
            payload["format"] = format
        return await self._request("PUT", f"/messages/{message_id}", data=payload)

    async def delete_message(self, message_id: int) -> Dict[str, Any]:
        """DELETE /messages/{messageId} — delete a message."""
        return await self._request("DELETE", f"/messages/{message_id}")

    async def get_message(self, message_id: int) -> Dict[str, Any]:
        """GET /messages/{messageId} — get a message."""
        return await self._request("GET", f"/messages/{message_id}")

    # ── Chat actions ────────────────────────────────────────────────────────

    async def send_chat_action(
        self,
        chat_id: int,
        action: str = "typing_on",
    ) -> Dict[str, Any]:
        """POST /chats/{chatId}/actions — send chat action.

        Common actions: 'typing_on', 'typing_off'
        """
        return await self._request(
            "POST",
            f"/chats/{chat_id}/actions",
            data={"action": action},
        )

    # ── Callback answer ────────────────────────────────────────────────────

    async def answer_callback(
        self,
        callback_id: str,
        text: Optional[str] = None,
        notification: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /callback — answer a callback query."""
        payload: Dict[str, Any] = {"callback_id": callback_id}
        if text:
            payload["text"] = text
        if notification:
            payload["notification"] = notification
        return await self._request("POST", "/callback", data=payload)

    # ── Subscriptions (Webhook) ────────────────────────────────────────────

    async def subscribe(
        self,
        url: str,
        update_types: Optional[List[str]] = None,
    ) -> SubscriptionResponse:
        """POST /subscriptions — register webhook."""
        if update_types is None:
            update_types = ["message_created", "message_callback"]

        payload = {"url": url, "update_types": update_types}
        body = await self._request("POST", "/subscriptions", data=payload)
        return SubscriptionResponse(
            id=body.get("id"),
            url=body.get("url"),
            ok=True,
        )

    async def unsubscribe(self, subscription_id: str) -> Dict[str, Any]:
        """DELETE /subscriptions/{id} — remove webhook."""
        return await self._request("DELETE", f"/subscriptions/{subscription_id}")

    async def get_subscriptions(self) -> List[Dict[str, Any]]:
        """GET /subscriptions — list all webhooks."""
        body = await self._request("GET", "/subscriptions")
        return body if isinstance(body, list) else body.get("subscriptions", [])

    # ── Long Polling ────────────────────────────────────────────────────────

    async def get_updates(
        self,
        offset: Optional[int] = None,
        limit: int = 100,
        timeout: int = 30,
    ) -> List[Dict[str, Any]]:
        """GET /updates — Long Polling for updates."""
        params: Dict[str, Any] = {"limit": limit, "timeout": timeout}
        if offset is not None:
            params["offset"] = offset

        query = "&".join(f"{k}={v}" for k, v in params.items())
        body = await self._request("GET", f"/updates?{query}")
        return body if isinstance(body, list) else body.get("updates", [])

    # ── Upload ──────────────────────────────────────────────────────────────

    async def upload_image(self, image_data: bytes) -> UploadResponse:
        """POST /upload/image — upload an image."""
        data = aiohttp.FormData()
        data.add_field(
            "file", image_data, filename="image.png", content_type="image/png"
        )
        body = await self._upload_request("/upload/image", data)
        return UploadResponse(**body)

    async def upload_audio(
        self,
        audio_data: bytes,
        file_name: str = "audio.ogg",
        content_type: str = "audio/ogg",
    ) -> UploadResponse:
        """POST /uploads — upload an audio file (voice message)."""
        data = aiohttp.FormData()
        data.add_field("file", audio_data, filename=file_name, content_type=content_type)
        logger.info("Uploading audio: %s (%d bytes)", file_name, len(audio_data))
        body = await self._upload_request("/uploads", data)
        return UploadResponse(**body)

    async def upload_file(
        self,
        file_data: bytes,
        file_name: str = "file",
        content_type: str = "application/octet-stream",
    ) -> UploadResponse:
        """POST /uploads — upload a generic file."""
        data = aiohttp.FormData()
        data.add_field("file", file_data, filename=file_name, content_type=content_type)
        logger.info("Uploading file: %s (%d bytes)", file_name, len(file_data))
        body = await self._upload_request("/uploads", data)
        return UploadResponse(**body)

    # ── Send media messages ────────────────────────────────────────────────

    async def send_audio_message(
        self,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        audio_token: str = "",
        text: str = "",
        reply_to: Optional[str] = None,
    ) -> SendMessageResponse:
        """POST /messages with audio attachment."""
        attachments = [{"type": "audio", "payload": {"token": audio_token}}]
        return await self.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=attachments,
            reply_to=reply_to,
        )

    async def send_image_message(
        self,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        image_token: str = "",
        text: str = "",
        reply_to: Optional[str] = None,
    ) -> SendMessageResponse:
        """POST /messages with image attachment."""
        attachments = [{"type": "image", "payload": {"token": image_token}}]
        return await self.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=attachments,
            reply_to=reply_to,
        )

    async def send_file_message(
        self,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        file_token: str = "",
        file_name: str = "",
        text: str = "",
        reply_to: Optional[str] = None,
    ) -> SendMessageResponse:
        """POST /messages with file attachment."""
        payload = {"token": file_token}
        if file_name:
            payload["name"] = file_name
        attachments = [{"type": "file", "payload": payload}]
        return await self.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=attachments,
            reply_to=reply_to,
        )

    # ── Download attachments ────────────────────────────────────────────────

    async def download_attachment(
        self,
        url: str,
        token: Optional[str] = None,
    ) -> bytes:
        """Download an attachment from MAX CDN.

        Args:
            url: Attachment URL from MAX API payload.
            token: Optional access token.

        Returns:
            Raw bytes of the downloaded file.
        """
        session = await self._get_session()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        logger.debug("Downloading attachment: %s", url[:100])
        async with session.get(url, headers=headers) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise MAXApiError(
                    "download_failed",
                    f"HTTP {resp.status}: {body[:200]}",
                    resp.status,
                )
            data = await resp.read()
            logger.info(
                "Downloaded attachment: %s (%d bytes)", url[:80], len(data)
            )
            return data

    async def download_attachment_to_file(
        self,
        url: str,
        dest_path: str,
        token: Optional[str] = None,
    ) -> str:
        """Download an attachment and save to a local file.

        Returns:
            Absolute path to the saved file.
        """
        import os

        data = await self.download_attachment(url, token=token)
        dest = os.path.abspath(dest_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        with open(dest, "wb") as f:
            f.write(data)

        logger.info("Saved attachment to: %s (%d bytes)", dest, len(data))
        return dest
