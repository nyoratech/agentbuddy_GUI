"""
Chat-history persistence + auth, exercised directly against the Reflex data
models (the same tables the UI reads/writes on login). Proves that a user, their
chats, messages and plots survive a "log out / log back in" round-trip.

Must run in its own process (Reflex patches sqlmodel on import) — see run_tests.sh.
"""
import os
import sys
import tempfile

_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
sys.path.insert(0, _FRONTEND)

import reflex as rx  # noqa: E402,F401  (import first so it patches sqlmodel)
from sqlmodel import SQLModel, Session, create_engine, select  # noqa: E402

from finbuddy.data_models.db_users import User, Chats, QAs, DataPlots  # noqa: E402
from finbuddy.utils.password_utils import hash_password, verify_password  # noqa: E402

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
engine = create_engine(f"sqlite:///{_db}")
SQLModel.metadata.create_all(engine)


def test_password_hash_roundtrip():
    h = hash_password("secret")
    assert h != "secret"
    assert verify_password("secret", h) is True
    assert verify_password("wrong", h) is False


def test_history_survives_relogin():
    # signup
    with Session(engine) as s:
        u = User(username="bob", password=hash_password("pw"))
        s.add(u)
        s.commit()
        s.refresh(u)
        uid = u.id

    # write a chat with a message and a plot (what the chat flow persists)
    with Session(engine) as s:
        c = Chats(chat_title="Research", user_id=uid)
        s.add(c)
        s.commit()
        s.refresh(c)
        s.add(QAs(question="what is beta?", answer="a risk measure", user_id=uid, chat_id=c.id))
        s.add(DataPlots(id=1, user_id=uid, chat_id=c.id, plot_name="p.csv",
                        column="v", xaxis="date", color="etf", title="Perf", nickname="Research"))
        s.commit()

    # "log back in": load everything for the user
    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "bob")).first()
        assert verify_password("pw", u.password)
        chats = s.exec(select(Chats).where(Chats.user_id == u.id)).all()
        assert len(chats) == 1
        qas = s.exec(select(QAs).where(QAs.chat_id == chats[0].id)).all()
        plots = s.exec(select(DataPlots).where(DataPlots.chat_id == chats[0].id)).all()
        assert qas[0].question == "what is beta?" and qas[0].answer == "a risk measure"
        assert plots[0].title == "Perf"
