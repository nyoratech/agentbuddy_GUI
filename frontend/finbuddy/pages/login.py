import reflex as rx
from finbuddy.layout.auth import auth_layout
from finbuddy.auth import AuthState


def oauth_popup_listener():
    """
    Script that listens for messages from OAuth popup windows.
    When authentication completes, the popup sends a message and closes.
    This listener then redirects to home if login was successful.
    """
    return rx.script(
        """
        window.addEventListener('message', function(event) {
            // Verify the message is from our callback pages
            if (event.data && event.data.type === 'oauth_callback') {
                if (event.data.success) {
                    // Authentication successful, redirect to home
                    window.location.href = '/';
                } else {
                    // Authentication failed, show error
                    alert(event.data.error || 'Authentication failed. Please try again.');
                }
            }
        });
        """
    )


def google_icon():
    """Google logo SVG icon."""
    return rx.html(
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="20" height="20">
            <path fill="#FFC107" d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12c0-6.627,5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24c0,11.045,8.955,20,20,20c11.045,0,20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z"/>
            <path fill="#FF3D00" d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z"/>
            <path fill="#4CAF50" d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z"/>
            <path fill="#1976D2" d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z"/>
        </svg>
        """
    )


def microsoft_icon():
    """Microsoft logo SVG icon."""
    return rx.html(
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" width="20" height="20">
            <rect x="1" y="1" width="9" height="9" fill="#f25022"/>
            <rect x="11" y="1" width="9" height="9" fill="#7fba00"/>
            <rect x="1" y="11" width="9" height="9" fill="#00a4ef"/>
            <rect x="11" y="11" width="9" height="9" fill="#ffb900"/>
        </svg>
        """
    )


def login():
    """The login page."""
    return auth_layout(
        rx.vstack(
            # OAuth popup listener script
            oauth_popup_listener(),
            # Welcome message and subtitle - moved up
            rx.vstack(
                rx.heading("Welcome back", size="6", color="white"),
                rx.text("Log in to your account", color="white"),
                spacing="1",
                align_items="center",
                padding_bottom="0.5vh",
                padding_top="0",
            ),
            # Login form
            rx.vstack(
                rx.input(
                    placeholder="Username",
                    on_blur=AuthState.set_username,
                    size="3",
                    width="100%",
                    background_color="white",
                ),
                rx.input(
                    type="password",
                    placeholder="Password",
                    on_blur=AuthState.set_password,
                    size="3",
                    width="100%",
                    background_color="white",
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.link(
                        "Forgot password?",
                        href="/reset-password",
                        color="rgba(255,255,255,0.7)",
                        font_size="12px",
                        _hover={"color": "white"},
                    ),
                    width="100%",
                ),
                rx.button("Log in", on_click=AuthState.login, width="100%", background_color="blue"),
                spacing="2",
                width="35%",
                align_items="center"
            ),
            # Divider with "or" - reduced spacing
            rx.hstack(
                rx.divider(width="30%", border_color="rgba(255,255,255,0.3)"),
                rx.text("or", color="rgba(255,255,255,0.7)", font_size="12px"),
                rx.divider(width="30%", border_color="rgba(255,255,255,0.3)"),
                width="35%",
                align_items="center",
                justify="center",
                padding_y="0.3vh",
            ),
            # OAuth buttons - horizontal small square icons aligned left
            rx.hstack(
                rx.button(
                    google_icon(),
                    on_click=AuthState.google_login,
                    width="40px",
                    height="40px",
                    min_width="40px",
                    padding="8px",
                    background_color="white",
                    _hover={"background_color": "#f0f0f0"},
                    cursor="pointer",
                    border_radius="8px",
                ),
                rx.button(
                    microsoft_icon(),
                    on_click=AuthState.microsoft_login,
                    width="40px",
                    height="40px",
                    min_width="40px",
                    padding="8px",
                    background_color="white",
                    _hover={"background_color": "#f0f0f0"},
                    cursor="pointer",
                    border_radius="8px",
                ),
                spacing="3",
                width="35%",
                justify="start",
            ),
            # Sign up link
            rx.text(
                rx.link("Don't have an account? Sign up here.", href="/signup"),
                color="gray",
                padding_top="0.5vh",
            ),
            spacing="1",
            width="100%",
            align_items="center"
        )
    )
