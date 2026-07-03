"""Main page: navbar + chat + notifications."""
import reflex as rx

from ..components.navbar import navbar
from ..components.chat import chat_panel
from ..components.notifications import notifications_panel


def index_page() -> rx.Component:
    return rx.vstack(
        navbar(),
        rx.hstack(
            rx.box(chat_panel(), flex="1", height="100%", min_width="0"),
            notifications_panel(),
            width="100%",
            flex="1",
            spacing="0",
            min_height="0",
        ),
        height="100vh",
        width="100%",
        spacing="0",
    )
