import reflex as rx
from finbuddy.components.chat_component import chat_container
from finbuddy.components.navbar import navbar, thin_sidebar


def index_page():
    """Main page: thin left rail + top navbar + central chat (with plots/tables).

    The full app also has a GUI page-builder view here (State.show_page_view);
    the minimal build keeps only the chat view.
    """
    return rx.box(
        thin_sidebar(),
        rx.grid(
            rx.box(navbar()),
            rx.box(
                chat_container(),
                min_height=0,
            ),
            grid_template_columns="1fr",
            grid_template_rows="auto 1fr",
            height="100%",
            width="100%",
            padding_left="60px",
            spacing="0",
        ),
        height="100vh",
        width="100vw",
    )
