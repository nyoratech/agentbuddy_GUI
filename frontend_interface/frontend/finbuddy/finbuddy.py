"""FinBuddy — minimal interface.

Registers only the pages the minimal build needs: the main chat page (central
chat with plots/tables, left chat-tree sidebar with folders + sharing, top
agents panel), plus login and signup. Everything else from the full app
(markets, stats, etf, agent builder, page builder, …) is intentionally left out.
"""
import reflex as rx

from finbuddy.pages.index import index_page
from finbuddy.pages.login import login
from finbuddy.pages.signup import signup
from finbuddy.state import State

app = rx.App(
    theme=rx.theme(
        appearance="light",
        background_color=rx.color("white", 3),
        color=rx.color("white", 12),
        has_background=True,
        radius="medium",
        accent_color="blue",
        gray_color="gray",
    ),
)

app.add_page(index_page, route="/", on_load=State.check_login())
app.add_page(login)
app.add_page(signup)
