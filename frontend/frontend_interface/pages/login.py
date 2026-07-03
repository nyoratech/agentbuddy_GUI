"""Login / signup page."""
import reflex as rx

from ..state import State


def login_page() -> rx.Component:
    return rx.center(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("bot-message-square", size=28, color=rx.color("blue", 9)),
                    rx.heading("FinBuddy", size="6"),
                    align="center",
                    spacing="2",
                ),
                rx.text("Minimal interface — sign in to continue.", size="2", color=rx.color("gray", 10)),
                rx.divider(),
                rx.input(
                    placeholder="Username",
                    value=State.username_input,
                    on_change=State.set_username_input,
                    width="100%",
                ),
                rx.input(
                    placeholder="Password",
                    type="password",
                    value=State.password_input,
                    on_change=State.set_password_input,
                    width="100%",
                ),
                rx.cond(
                    State.auth_error != "",
                    rx.callout(State.auth_error, icon="triangle_alert", color_scheme="red", size="1", width="100%"),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.button("Log in", on_click=State.do_login, width="100%"),
                    rx.button("Sign up", on_click=State.do_signup, variant="soft", width="100%"),
                    width="100%",
                    spacing="2",
                ),
                rx.text("Demo account: demo / demo", size="1", color=rx.color("gray", 9)),
                spacing="3",
                width="22em",
            ),
            padding="2em",
        ),
        height="100vh",
        background_color=rx.color("gray", 2),
    )
