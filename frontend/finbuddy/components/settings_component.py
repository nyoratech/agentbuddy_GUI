"""Settings/Configuration page component."""

import reflex as rx
from finbuddy.state import State


def settings_header() -> rx.Component:
    """Header section of the settings page."""
    return rx.hstack(
        rx.vstack(
            rx.heading("Settings", size="6", weight="medium", color="#1f2937"),
            rx.text(
                "Manage your account and preferences",
                font_size="14px",
                color="#6b7280",
            ),
            spacing="1",
            align_items="start",
        ),
        width="100%",
        padding="24px",
        border_bottom="1px solid #e5e7eb",
    )


def profile_section() -> rx.Component:
    """User profile information section."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("user", size=18, color="#3b82f6"),
                rx.text("Profile", font_size="15px", font_weight="500", color="#374151"),
                spacing="2",
                align_items="center",
            ),
            rx.divider(margin_y="12px"),
            # Username row
            rx.hstack(
                rx.text("Username", font_size="13px", color="#6b7280", width="120px"),
                rx.text(
                    State.user.username,
                    font_size="14px",
                    font_weight="500",
                    color="#1f2937",
                ),
                width="100%",
                align_items="center",
            ),
            # User ID row
            rx.hstack(
                rx.text("User ID", font_size="13px", color="#6b7280", width="120px"),
                rx.badge(
                    State.user.id,
                    color_scheme="gray",
                    size="1",
                ),
                width="100%",
                align_items="center",
            ),
            # Created at row
            rx.hstack(
                rx.text("Member since", font_size="13px", color="#6b7280", width="120px"),
                rx.text(
                    "Account created",
                    font_size="13px",
                    color="#9ca3af",
                ),
                width="100%",
                align_items="center",
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        background="#ffffff",
        border_radius="12px",
        border="1px solid #e5e7eb",
        _hover={"border_color": "#d1d5db"},
        transition="border-color 0.2s",
    )


def groups_section() -> rx.Component:
    """User groups section."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("users", size=18, color="#8b5cf6"),
                rx.text("Groups", font_size="15px", font_weight="500", color="#374151"),
                rx.spacer(),
                rx.badge(
                    State.user_groups_list.length(),
                    color_scheme="purple",
                    size="1",
                ),
                width="100%",
                align_items="center",
            ),
            rx.divider(margin_y="12px"),
            rx.cond(
                State.user_groups_list.length() > 0,
                rx.vstack(
                    rx.foreach(
                        State.user_groups_list,
                        lambda group: rx.hstack(
                            rx.box(
                                rx.icon("users", size=14, color="#8b5cf6"),
                                padding="8px",
                                background="#f3e8ff",
                                border_radius="8px",
                            ),
                            rx.vstack(
                                rx.text(
                                    group["group_name"],
                                    font_size="14px",
                                    font_weight="500",
                                    color="#1f2937",
                                ),
                                rx.text(
                                    f"ID: {group['group_id'][:8]}...",
                                    font_size="11px",
                                    color="#9ca3af",
                                ),
                                spacing="0",
                                align_items="start",
                            ),
                            spacing="3",
                            align_items="center",
                            width="100%",
                            padding="8px",
                            border_radius="8px",
                            _hover={"background": "#f9fafb"},
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.hstack(
                    rx.icon("users", size=16, color="#d1d5db"),
                    rx.text(
                        "You are not a member of any groups",
                        font_size="13px",
                        color="#9ca3af",
                    ),
                    spacing="2",
                    padding="16px",
                    background="#f9fafb",
                    border_radius="8px",
                    width="100%",
                    justify_content="center",
                ),
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        background="#ffffff",
        border_radius="12px",
        border="1px solid #e5e7eb",
        _hover={"border_color": "#d1d5db"},
        transition="border-color 0.2s",
    )


def company_section() -> rx.Component:
    """Company/Organization section."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("building-2", size=18, color="#f59e0b"),
                rx.text("Organization", font_size="15px", font_weight="500", color="#374151"),
                spacing="2",
                align_items="center",
            ),
            rx.divider(margin_y="12px"),
            rx.hstack(
                rx.text("Company", font_size="13px", color="#6b7280", width="120px"),
                rx.text(
                    State.user.username,  # Using username as company for now
                    font_size="14px",
                    color="#1f2937",
                ),
                width="100%",
                align_items="center",
            ),
            rx.hstack(
                rx.text("Role", font_size="13px", color="#6b7280", width="120px"),
                rx.badge("Member", color_scheme="blue", size="1"),
                width="100%",
                align_items="center",
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        background="#ffffff",
        border_radius="12px",
        border="1px solid #e5e7eb",
        _hover={"border_color": "#d1d5db"},
        transition="border-color 0.2s",
    )


def preferences_section() -> rx.Component:
    """User preferences section - placeholder for future settings."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("sliders-horizontal", size=18, color="#10b981"),
                rx.text("Preferences", font_size="15px", font_weight="500", color="#374151"),
                spacing="2",
                align_items="center",
            ),
            rx.divider(margin_y="12px"),
            # Notification preferences
            rx.hstack(
                rx.vstack(
                    rx.text("Email Notifications", font_size="14px", color="#374151"),
                    rx.text(
                        "Receive email alerts for triggers",
                        font_size="12px",
                        color="#9ca3af",
                    ),
                    spacing="0",
                    align_items="start",
                ),
                rx.spacer(),
                rx.switch(size="2", disabled=True),
                width="100%",
                align_items="center",
                padding_y="8px",
            ),
            rx.divider(margin_y="4px", opacity="0.5"),
            # Theme preference
            rx.hstack(
                rx.vstack(
                    rx.text("Dark Mode", font_size="14px", color="#374151"),
                    rx.text(
                        "Switch to dark theme",
                        font_size="12px",
                        color="#9ca3af",
                    ),
                    spacing="0",
                    align_items="start",
                ),
                rx.spacer(),
                rx.switch(size="2", disabled=True),
                width="100%",
                align_items="center",
                padding_y="8px",
            ),
            rx.divider(margin_y="4px", opacity="0.5"),
            # Auto-refresh preference
            rx.hstack(
                rx.vstack(
                    rx.text("Auto-refresh Data", font_size="14px", color="#374151"),
                    rx.text(
                        "Automatically refresh market data",
                        font_size="12px",
                        color="#9ca3af",
                    ),
                    spacing="0",
                    align_items="start",
                ),
                rx.spacer(),
                rx.switch(size="2", disabled=True),
                width="100%",
                align_items="center",
                padding_y="8px",
            ),
            # Coming soon badge
            rx.hstack(
                rx.icon("clock", size=14, color="#9ca3af"),
                rx.text(
                    "More preferences coming soon",
                    font_size="12px",
                    color="#9ca3af",
                    font_style="italic",
                ),
                spacing="2",
                margin_top="8px",
            ),
            spacing="2",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        background="#ffffff",
        border_radius="12px",
        border="1px solid #e5e7eb",
        _hover={"border_color": "#d1d5db"},
        transition="border-color 0.2s",
    )


def legal_section() -> rx.Component:
    """Legal documents section with links to Terms and Disclaimer."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("file-text", size=18, color="#6366f1"),
                rx.text("Legal", font_size="15px", font_weight="500", color="#374151"),
                spacing="2",
                align_items="center",
            ),
            rx.divider(margin_y="12px"),
            # Terms of Service link
            rx.link(
                rx.hstack(
                    rx.vstack(
                        rx.text("Terms of Service", font_size="14px", color="#374151"),
                        rx.text(
                            "View our terms and conditions",
                            font_size="12px",
                            color="#9ca3af",
                        ),
                        spacing="0",
                        align_items="start",
                    ),
                    rx.spacer(),
                    rx.icon("external-link", size=16, color="#9ca3af"),
                    width="100%",
                    align_items="center",
                    padding_y="8px",
                    _hover={"background": "#f9fafb"},
                    border_radius="8px",
                    padding_x="8px",
                ),
                href="/terms-of-service",
                is_external=True,
                width="100%",
                _hover={"text_decoration": "none"},
            ),
            rx.divider(margin_y="4px", opacity="0.5"),
            # Disclaimer link
            rx.link(
                rx.hstack(
                    rx.vstack(
                        rx.text("Disclaimer & Risk Disclosure", font_size="14px", color="#374151"),
                        rx.text(
                            "Important information about risks",
                            font_size="12px",
                            color="#9ca3af",
                        ),
                        spacing="0",
                        align_items="start",
                    ),
                    rx.spacer(),
                    rx.icon("external-link", size=16, color="#9ca3af"),
                    width="100%",
                    align_items="center",
                    padding_y="8px",
                    _hover={"background": "#f9fafb"},
                    border_radius="8px",
                    padding_x="8px",
                ),
                href="/disclaimer",
                is_external=True,
                width="100%",
                _hover={"text_decoration": "none"},
            ),
            spacing="2",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        background="#ffffff",
        border_radius="12px",
        border="1px solid #e5e7eb",
        _hover={"border_color": "#d1d5db"},
        transition="border-color 0.2s",
    )


def danger_zone_section() -> rx.Component:
    """Danger zone section for account actions."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("triangle_alert", size=18, color="#ef4444"),
                rx.text("Danger Zone", font_size="15px", font_weight="500", color="#ef4444"),
                spacing="2",
                align_items="center",
            ),
            rx.divider(margin_y="12px"),
            rx.hstack(
                rx.vstack(
                    rx.text("Delete Account", font_size="14px", color="#374151"),
                    rx.text(
                        "Permanently delete your account and all data",
                        font_size="12px",
                        color="#9ca3af",
                    ),
                    spacing="0",
                    align_items="start",
                ),
                rx.spacer(),
                rx.button(
                    "Delete",
                    variant="outline",
                    color_scheme="red",
                    size="2",
                    disabled=True,
                ),
                width="100%",
                align_items="center",
            ),
            spacing="3",
            align_items="start",
            width="100%",
        ),
        padding="20px",
        background="#fef2f2",
        border_radius="12px",
        border="1px solid #fecaca",
    )


def settings_main_content() -> rx.Component:
    """Main content area for settings."""
    return rx.box(
        rx.vstack(
            settings_header(),
            rx.box(
                rx.vstack(
                    # Two-column grid for sections
                    rx.grid(
                        profile_section(),
                        groups_section(),
                        company_section(),
                        preferences_section(),
                        legal_section(),
                        columns="2",
                        spacing="4",
                        width="100%",
                    ),
                    # Danger zone full width
                    danger_zone_section(),
                    spacing="4",
                    width="100%",
                    max_width="900px",
                ),
                padding="24px",
                width="100%",
                overflow_y="auto",
            ),
            spacing="0",
            width="100%",
            height="100%",
        ),
        flex="1",
        background="#f9fafb",
        height="calc(100vh - 60px)",
        overflow_y="auto",
    )


def settings_container() -> rx.Component:
    """Main container for settings page."""
    return rx.box(
        settings_main_content(),
        width="100%",
        height="calc(100vh - 60px)",
    )
