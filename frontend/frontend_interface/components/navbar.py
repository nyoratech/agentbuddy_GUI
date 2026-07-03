"""Top navigation bar."""
import reflex as rx

from ..state import State


def navbar() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.icon("bot-message-square", size=24, color=rx.color("blue", 9)),
            rx.heading("FinBuddy", size="5"),
            rx.badge("minimal", variant="soft", color_scheme="gray"),
            align="center",
            spacing="2",
        ),
        rx.spacer(),
        rx.hstack(
            rx.cond(
                State.processing,
                rx.hstack(rx.spinner(size="1"), rx.text("working…", size="2"), spacing="1", align="center"),
                rx.fragment(),
            ),
            rx.text(State.user_id, size="2", color=rx.color("gray", 11)),
            rx.button("Logout", on_click=State.logout, variant="soft", size="2"),
            align="center",
            spacing="3",
        ),
        width="100%",
        padding="0.75em 1.25em",
        border_bottom=f"1px solid {rx.color('gray', 5)}",
        align="center",
        background_color=rx.color("gray", 1),
    )
