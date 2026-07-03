"""
Seed a demo user (demo / demo) into the Reflex DB so you can log in immediately.

Run AFTER `reflex db migrate` (the tables must exist). Safe to run repeatedly —
it is a no-op if the user already exists.
"""
import reflex as rx  # noqa: F401  (import first so it patches sqlmodel)
from sqlmodel import Session, create_engine, select

from rxconfig import config
from finbuddy.data_models.db_users import User, ChatDirectory
from finbuddy.utils.password_utils import hash_password


def main() -> None:
    engine = create_engine(config.db_url)
    with Session(engine) as session:
        if session.exec(select(User).where(User.username == "demo")).first():
            print("[seed] demo user already exists")
            return
        user = User(username="demo", password=hash_password("demo"))
        session.add(user)
        session.commit()
        session.refresh(user)
        # the login flow expects a "Shared with you" directory to exist
        session.add(ChatDirectory(user_id=user.id, name="Shared with you",
                                  parent_id=None, order=9999))
        session.commit()
        print("[seed] created demo user: demo / demo")


if __name__ == "__main__":
    main()
