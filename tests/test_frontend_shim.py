"""
Tests for the frontend shim layer that lets the original finbuddy UI run against
the mock backend without the full YourIndexingAI / db_light packages.
"""
import os
import sys

_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
sys.path.insert(0, _FRONTEND)

from YourIndexingAI.modules.modules_utils import (  # noqa: E402
    extract_tag_content, replace_expection, process_table,
)
from YourIndexingAI.rx_interface import (  # noqa: E402
    init_bot, list_saved_portfolios, load_images_from_directory, pool_jobids,
)
from db_light.auth import verification_service as vs  # noqa: E402
from db_light.auth.auth_db import ensure_user_exists  # noqa: E402


# --- modules_utils --------------------------------------------------------- #
def test_extract_tag_content():
    assert extract_tag_content("<final_answer>hi</final_answer>", "final_answer") == "hi"
    assert extract_tag_content("nothing here", "final_answer") is None


def test_process_table_strips_table_blocks():
    assert "keep" in process_table("keep ```TABLE x ``` end")
    assert "TABLE" not in process_table("```TABLE secret```")


def test_replace_expection_newlines_to_br():
    assert "<br>" in replace_expection("line1\nline2")


# --- rx_interface storage stubs ------------------------------------------- #
def test_storage_stubs_return_safe_empties():
    assert list_saved_portfolios("alice") == []
    assert load_images_from_directory("alice") == []
    assert pool_jobids([], "alice") == {}


def test_init_bot_returns_mockbot():
    bot = init_bot()
    assert hasattr(bot, "FB_super_agent")


# --- verification_service (in-memory) ------------------------------------- #
def test_verification_flow():
    ok, _, code = vs.create_pending_verification("a@b.com")
    assert ok and len(code) == 6
    assert vs.verify_code("a@b.com", code) == (True, "Email verified")
    # code is single-use
    assert vs.verify_code("a@b.com", code)[0] is False


def test_verification_rejects_wrong_code():
    vs.create_pending_verification("c@d.com")
    assert vs.verify_code("c@d.com", "000000")[0] is False


# --- auth_db graceful without Postgres ------------------------------------ #
def test_ensure_user_exists_no_postgres(monkeypatch):
    # Point at a dead host so it cannot connect; must return False, not raise.
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "1")
    assert ensure_user_exists("nobody") is False
