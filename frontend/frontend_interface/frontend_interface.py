"""FinBuddy — minimal Reflex frontend entry point."""
import reflex as rx

from .state import State
from .pages.index import index_page
from .pages.login import login_page

app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        gray_color="slate",
        radius="medium",
    ),
)

app.add_page(index_page, route="/", on_load=State.on_load_index)
app.add_page(login_page, route="/login")
