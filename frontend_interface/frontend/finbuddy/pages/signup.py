import reflex as rx
from finbuddy.layout.auth import auth_layout
from finbuddy.auth import AuthState


def email_step():
    """Step 1: Enter email to receive verification code."""
    return rx.vstack(
        rx.vstack(
            rx.heading("Create an account", size="6", color="white"),
            rx.text("Enter your email to get started", color="white"),
            spacing="1",
            align_items="center",
            padding_bottom="2vh",
            padding_top="1vh",
        ),
        rx.input(
            placeholder="Email address",
            on_blur=AuthState.set_email,
            type="email",
            size="3",
            width="50%",
            background_color="white",
        ),
        # Error message
        rx.cond(
            AuthState.signup_error != "",
            rx.text(
                AuthState.signup_error,
                color="red",
                font_size="14px",
            ),
        ),
        rx.button(
            rx.cond(
                AuthState.signup_loading,
                rx.spinner(size="1"),
                rx.text("Send Verification Code"),
            ),
            on_click=AuthState.send_verification,
            width="50%",
            background_color="blue",
            disabled=AuthState.signup_loading,
        ),
        rx.text(
            "Already have an account? ",
            rx.link("Sign in here.", href="/"),
            color="gray",
        ),
        spacing="2",
        width="100%",
        align_items="center",
    )


def verification_step():
    """Step 2: Enter verification code and account details."""
    return rx.vstack(
        rx.vstack(
            rx.heading("Verify your email", size="6", color="white"),
            rx.text("Enter the code sent to:", color="white"),
            rx.text(AuthState.email, color="white", font_weight="bold"),
            spacing="1",
            align_items="center",
            padding_bottom="1vh",
            padding_top="1vh",
        ),
        rx.input(
            placeholder="Verification code (6 digits)",
            on_blur=AuthState.set_verification_code,
            size="2",
            width="50%",
            background_color="white",
            max_length=6,
        ),
        # Username with check button
        rx.hstack(
            rx.input(
                placeholder="Username",
                value=AuthState.username,
                on_change=[AuthState.set_username, AuthState.reset_username_check],
                size="2",
                width="100%",
                background_color="white",
            ),
            rx.button(
                "Check",
                on_click=AuthState.check_username_availability,
                size="2",
                background_color=rx.cond(
                    AuthState.username_available,
                    "green",
                    "gray"
                ),
                color="white",
            ),
            width="50%",
            spacing="2",
        ),
        # Username availability message
        rx.cond(
            AuthState.username_check_message != "",
            rx.text(
                AuthState.username_check_message,
                color=rx.cond(
                    AuthState.username_available,
                    "lightgreen",
                    "orange"
                ),
                font_size="12px",
            ),
        ),
        rx.input(
            type="password",
            placeholder="Password",
            on_blur=AuthState.set_password,
            size="2",
            width="50%",
            background_color="white",
        ),
        rx.input(
            type="password",
            placeholder="Confirm password",
            on_blur=AuthState.set_confirm_password,
            size="2",
            width="50%",
            background_color="white",
        ),
        # Terms and Conditions checkbox
        rx.hstack(
            rx.checkbox(
                checked=AuthState.terms_accepted,
                on_change=AuthState.set_terms_accepted,
                color_scheme="blue",
            ),
            rx.text(
                "I agree to the ",
                rx.link(
                    "Terms of Service",
                    href="/terms-of-service",
                    color="lightblue",
                    is_external=True,
                ),
                " and ",
                rx.link(
                    "Disclaimer",
                    href="/disclaimer",
                    color="lightblue",
                    is_external=True,
                ),
                color="white",
                font_size="12px",
            ),
            width="50%",
            spacing="2",
            align_items="center",
        ),
        # Error message
        rx.cond(
            AuthState.signup_error != "",
            rx.text(
                AuthState.signup_error,
                color="red",
                font_size="14px",
            ),
        ),
        rx.button(
            rx.cond(
                AuthState.signup_loading,
                rx.spinner(size="1"),
                rx.text("Create Account"),
            ),
            on_click=AuthState.complete_signup,
            width="50%",
            background_color="blue",
            disabled=rx.cond(
                AuthState.terms_accepted,
                AuthState.signup_loading,
                True,
            ),
        ),
        rx.hstack(
            rx.button(
                "Resend Code",
                on_click=AuthState.resend_verification,
                variant="ghost",
                color="white",
                size="1",
            ),
            rx.text("|", color="gray"),
            rx.button(
                "Change Email",
                on_click=AuthState.go_back_to_email,
                variant="ghost",
                color="white",
                size="1",
            ),
            spacing="2",
        ),
        rx.text(
            "Already have an account? ",
            rx.link("Sign in here.", href="/"),
            color="gray",
        ),
        spacing="2",
        width="100%",
        align_items="center",
    )


def signup():
    """The sign up page with email verification."""
    return auth_layout(
        rx.cond(
            AuthState.signup_step == 1,
            email_step(),
            verification_step(),
        )
    )
