"""Tests for MAX Hermes Plugin adapter."""

import pytest
from plugins.platforms.max.adapter import MaxAdapter, _verify_webhook_signature


class TestMaxAdapter:
    def test_adapter_import(self):
        """Test that adapter can be imported."""
        assert MaxAdapter is not None

    def test_adapter_has_required_methods(self):
        """Test that adapter has all required methods."""
        assert hasattr(MaxAdapter, "connect")
        assert hasattr(MaxAdapter, "disconnect")
        assert hasattr(MaxAdapter, "send")
        assert hasattr(MaxAdapter, "send_typing")
        assert hasattr(MaxAdapter, "send_image")

    def test_verify_webhook_signature_no_secret(self):
        """Without signature/secret, should pass."""
        assert _verify_webhook_signature(b"body", "", "")

    def test_verify_webhook_signature_valid(self):
        """Valid signature should pass."""
        import hashlib
        import hmac

        secret = "test_secret"
        body = b"test body"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_webhook_signature(body, sig, secret)

    def test_verify_webhook_signature_invalid(self):
        """Invalid signature should fail."""
        assert not _verify_webhook_signature(b"body", "bad_sig", "secret")
