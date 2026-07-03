"""Settings page."""

import reflex as rx
from finbuddy.components.navbar import navbar, thin_sidebar
from finbuddy.components.settings_component import settings_container


def settings_page() -> rx.Component:
    """The settings page."""
    return rx.fragment(
        navbar(),
        rx.hstack(
            thin_sidebar(),
            rx.box(
                settings_container(),
                margin_left="60px",
                width="calc(100% - 60px)",
            ),
            width="100%",
            spacing="0",
        ),
    )
