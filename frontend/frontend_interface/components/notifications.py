"""Notifications feed panel (right-hand side)."""
import reflex as rx

from ..state import State, Notif

_STATUS_COLOR = {
    "in_progress": "amber",
    "completed": "grass",
    "queued": "gray",
    "failed": "tomato",
}


def _notification(n: Notif) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(n.status, color_scheme="blue", variant="soft"),
            rx.spacer(),
            rx.text(n.time, size="1", color=rx.color("gray", 10)),
            width="100%",
            align="center",
        ),
        rx.text(n.text, size="2", margin_top="0.25em"),
        rx.text(f"job {n.job_id[:8]}", size="1", color=rx.color("gray", 9), margin_top="0.25em"),
        padding="0.75em",
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="8px",
        background_color=rx.color("gray", 1),
        width="100%",
    )


def notifications_panel() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading("Notifications", size="4"),
            rx.spacer(),
            rx.badge(State.unread_count, color_scheme="crimson"),
            rx.button(
                rx.icon("trash-2", size=14),
                on_click=State.clear_notifications,
                variant="ghost",
                size="1",
            ),
            width="100%",
            align="center",
        ),
        rx.divider(),
        rx.cond(
            State.notifications,
            rx.vstack(
                rx.foreach(State.notifications, _notification),
                spacing="2",
                width="100%",
            ),
            rx.text(
                "No notifications yet. Send a message to kick off a background job.",
                size="2",
                color=rx.color("gray", 10),
            ),
        ),
        width="320px",
        height="100%",
        padding="1em",
        spacing="3",
        border_left=f"1px solid {rx.color('gray', 5)}",
        overflow_y="auto",
    )
