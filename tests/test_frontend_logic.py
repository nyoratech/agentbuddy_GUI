"""
Tests for the frontend's notification-handling logic.

`State._apply_notification` is pure with respect to `self.messages` /
`self.notifications`, so we exercise it by binding it to a light stand-in
object — no Reflex runtime needed.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))

from frontend_interface.state import State, Msg, Notif  # noqa: E402


def _fake_state(messages):
    return types.SimpleNamespace(messages=messages, notifications=[])


def test_progress_updates_bubble_and_feed():
    msgs = [
        Msg(role="user", content="hi"),
        Msg(role="assistant", content="⏳ _queued…_", job_id="job1", status="queued"),
    ]
    st = _fake_state(msgs)
    State._apply_notification(st, {"job_id": "job1", "status": "in_progress", "result": "Working... step 1/3"})

    # bubble updated
    assert st.messages[1].status == "in_progress"
    assert "Working... step 1/3" in st.messages[1].content
    # feed got an entry
    assert len(st.notifications) == 1
    assert st.notifications[0].status == "in_progress"


def test_completion_sets_final_answer():
    msgs = [Msg(role="assistant", content="⏳", job_id="job1", status="in_progress")]
    st = _fake_state(msgs)
    State._apply_notification(st, {"job_id": "job1", "status": "completed", "result": "final answer"})
    assert st.messages[0].status == "completed"
    assert st.messages[0].content == "final answer"


def test_notification_for_unknown_job_is_still_recorded():
    st = _fake_state([Msg(role="assistant", content="x", job_id="jobA", status="in_progress")])
    State._apply_notification(st, {"job_id": "other", "status": "completed", "result": "hi"})
    # unrelated bubble untouched
    assert st.messages[0].status == "in_progress"
    # but the feed still records it
    assert len(st.notifications) == 1


def test_feed_is_prepended_newest_first():
    st = _fake_state([])
    State._apply_notification(st, {"job_id": "j", "status": "in_progress", "result": "first"})
    State._apply_notification(st, {"job_id": "j", "status": "completed", "result": "second"})
    assert st.notifications[0].text == "second"
    assert st.notifications[1].text == "first"
