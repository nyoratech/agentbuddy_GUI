"""
Seed ready-to-use demo accounts into the Reflex DB so you can log in immediately
— no signup / email verification (which would need a working SMTP server).

Accounts (log in with the email as the username):
    demo1@demo.com  / demo1
    demo2@demo2.com / demo2
    demo3@demo.com  / demo3

Run AFTER `reflex db migrate` (the tables must exist). Safe to run repeatedly —
existing users are skipped.
"""
import reflex as rx  # noqa: F401  (import first so it patches sqlmodel)
from sqlmodel import Session, create_engine, select

from rxconfig import config
from finbuddy.data_models.db_users import User, ChatDirectory
from finbuddy.utils.password_utils import hash_password

DEMO_USERS = [
    ("demo1@demo.com", "demo1"),
    ("demo2@demo2.com", "demo2"),
    ("demo3@demo.com", "demo3"),
]


def main() -> None:
    engine = create_engine(config.db_url)
    with Session(engine) as session:
        for email, password in DEMO_USERS:
            if session.exec(select(User).where(User.username == email)).first():
                print(f"[seed] {email} already exists")
                continue
            user = User(username=email, email=email, password=hash_password(password))
            session.add(user)
            session.commit()
            session.refresh(user)
            # the login flow expects a "Shared with you" directory to exist
            session.add(ChatDirectory(user_id=user.id, name="Shared with you",
                                      parent_id=None, order=9999))
            session.commit()
            print(f"[seed] created {email} / {password}")


if __name__ == "__main__":
    main()
