"""Test the mock agent reply generation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.worker import mock_agent_reply  # noqa: E402


def test_mock_reply_echoes_prompt():
    out = mock_agent_reply("analyse my portfolio")
    assert "analyse my portfolio" in out
    assert "mock agent" in out


def test_mock_reply_handles_empty():
    assert isinstance(mock_agent_reply(""), str)
    assert isinstance(mock_agent_reply(None), str)
