"""Tests for MAX Hermes Plugin adapter."""

import pytest
from plugins.platforms.max.adapter import MAXAdapter


class TestMAXAdapter:
    def test_adapter_import(self):
        """Test that adapter can be imported."""
        assert MAXAdapter is not None

    def test_adapter_has_required_methods(self):
        """Test that adapter has all required methods."""
        assert hasattr(MAXAdapter, "send_message")
        assert hasattr(MAXAdapter, "get_updates")
