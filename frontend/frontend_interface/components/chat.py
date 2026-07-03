"""Chat transcript + input bar."""
import reflex as rx

from ..state import State, Msg

_MESSAGE_STYLE = dict(padding="0.9em 1.1em", border_radius="12px", max_width="80%")


def _message(msg: Msg) -> rx.Component:
    is_user = msg.role == "user"
    return rx.box(
        rx.box(
            rx.markdown(msg.content),
            background_color=rx.cond(is_user, rx.color("blue", 4), rx.color("gray", 3)),
            color=rx.color("gray", 12),
            **_MESSAGE_STYLE,
        ),
        display="flex",
        justify_content=rx.cond(is_user, "flex-end", "flex-start"),
        width="100%",
        margin_y="0.4em",
    )


def _transcript() -> rx.Component:
    return rx.vstack(
        rx.cond(
            State.messages,
            rx.foreach(State.messages, _message),
            rx.center(
                rx.vstack(
                    rx.icon("messages-square", size=40, color=rx.color("gray", 8)),
                    rx.text("Ask me anything to start.", color=rx.color("gray", 10)),
                    rx.text(
                        "Each message is sent to the backend, queued as a background "
                        "job, and answered via a RabbitMQ notification.",
                        size="1",
                        color=rx.color("gray", 9),
                        max_width="30em",
                        text_align="center",
                    ),
                    spacing="2",
                    align="center",
                ),
                height="60vh",
            ),
        ),
        width="100%",
        spacing="1",
    )


def _input_bar() -> rx.Component:
    return rx.form(
        rx.hstack(
            rx.text_area(
                placeholder="Type a message…",
                name="question",
                value=State.question,
                on_change=State.set_question,
                flex="1",
                rows="2",
                auto_height=True,
                background_color=rx.color("gray", 2),
            ),
            rx.button(
                rx.cond(State.processing, rx.spinner(), rx.icon("send-horizontal")),
                type="submit",
                disabled=State.processing,
                height="100%",
                min_width="4em",
            ),
            width="100%",
            spacing="2",
            align="end",
        ),
        on_submit=State.send_message,
        reset_on_submit=True,
        width="100%",
    )


def chat_panel() -> rx.Component:
    return rx.vstack(
        rx.box(_transcript(), flex="1", width="100%", overflow_y="auto", padding="1em"),
        rx.box(
            _input_bar(),
            width="100%",
            padding="1em",
            border_top=f"1px solid {rx.color('gray', 5)}",
        ),
        height="100%",
        width="100%",
        spacing="0",
    )
