import reflex as rx
from finbuddy.state import State, DirectoryInfo
#from reflex.components import lucide
from finbuddy.components.prompts import *
from typing import Dict, Any, List


def render_news_feed_notification(notification: Dict[str, Any]) -> rx.Component:
    """Render a single notification item in the news feed dropdown."""
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(
                    notification["trigger_request"],
                    font_size="12px",
                    color="white",
                    font_weight="500",
                    no_of_lines=1,
                ),
                rx.hstack(
                    rx.icon("database", size=10, color=rx.color("blue", 9)),
                    rx.text(
                        notification["dataset_name"],
                        font_size="10px",
                        color=rx.color("mauve", 9),
                    ),
                    rx.text("|", font_size="10px", color=rx.color("mauve", 7)),
                    rx.text(
                        notification["row_count"],
                        font_size="10px",
                        color=rx.color("blue", 9),
                    ),
                    rx.text(
                        " rows",
                        font_size="10px",
                        color=rx.color("mauve", 9),
                    ),
                    spacing="1",
                    align_items="center",
                ),
                rx.text(
                    notification["created_at"],
                    font_size="9px",
                    color=rx.color("mauve", 8),
                ),
                spacing="0",
                align_items="start",
                width="100%",
            ),
            rx.button(
                rx.icon(tag="check", size=12),
                variant="ghost",
                size="1",
                color="white",
                on_click=lambda: State.mark_notification_read(notification["id"]),
                title="Mark as read",
            ),
            spacing="2",
            width="100%",
            align_items="start",
        ),
        padding="8px 12px",
        width="100%",
        _hover={"background": rx.color("blue", 10)},
        cursor="pointer",
    )


def news_feed_bell() -> rx.Component:
    """News feed bell icon with badge and dropdown for unread notifications."""
    return rx.popover.root(
        rx.popover.trigger(
            rx.box(
                rx.icon(tag="bell", size=18, color="white"),
                # Badge with unread count
                rx.cond(
                    State.has_unread_notifications,
                    rx.box(
                        rx.text(
                            State.unread_count,
                            font_size="9px",
                            color="white",
                            font_weight="bold",
                        ),
                        position="absolute",
                        top="-4px",
                        right="-4px",
                        min_width="16px",
                        height="16px",
                        background="#ef4444",
                        border_radius="50%",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        padding="0 4px",
                    ),
                    rx.box(),
                ),
                position="relative",
                cursor="pointer",
                padding="6px",
                border_radius="6px",
                _hover={"background": rx.color("blue", 10)},
            ),
        ),
        rx.popover.content(
            rx.vstack(
                # Header
                rx.hstack(
                    rx.text("Notifications", font_weight="600", font_size="14px", color="white"),
                    rx.spacer(),
                    rx.cond(
                        State.has_unread_notifications,
                        rx.button(
                            rx.text("Mark all read", font_size="11px"),
                            variant="ghost",
                            size="1",
                            color="white",
                            on_click=State.mark_all_notifications_read,
                        ),
                        rx.box(),
                    ),
                    width="100%",
                    align_items="center",
                    padding_bottom="8px",
                    border_bottom=f"1px solid {rx.color('blue', 10)}",
                ),
                # Notifications list
                rx.cond(
                    State.has_unread_notifications,
                    rx.box(
                        rx.foreach(
                            State.unread_notifications,
                            render_news_feed_notification,
                        ),
                        width="100%",
                        max_height="300px",
                        overflow_y="auto",
                    ),
                    rx.vstack(
                        rx.icon("bell-off", size=24, color=rx.color("mauve", 8)),
                        rx.text("No new notifications", font_size="12px", color=rx.color("mauve", 8)),
                        spacing="2",
                        align_items="center",
                        padding_y="16px",
                    ),
                ),
                # Footer link to notifications page
                rx.hstack(
                    rx.link(
                        rx.hstack(
                            rx.text("View all notifications", font_size="11px", color=rx.color("blue", 9)),
                            rx.icon("external-link", size=10, color=rx.color("blue", 9)),
                            spacing="1",
                            align_items="center",
                        ),
                        href="/notifications",
                    ),
                    width="100%",
                    justify_content="center",
                    padding_top="8px",
                    border_top=f"1px solid {rx.color('blue', 10)}",
                ),
                spacing="2",
                width="280px",
                padding="12px",
            ),
            background_color=rx.color("blue", 11),
            border=f"1px solid {rx.color('blue', 10)}",
        ),
        on_open_change=State.toggle_news_feed_dropdown,
    )


def render_container_menu_item(container: Dict[str, str]) -> rx.Component:
    """Render a single container menu item with share button."""
    container_id = container["id"]
    container_name = container["name"]

    return rx.menu.item(
        rx.hstack(
            rx.icon(tag="circle", size=10, color="green"),
            rx.text(container_name, font_size="12px"),
            rx.text(container["instance_type"], font_size="10px", color=rx.color("mauve", 9)),
            rx.spacer(),
            # Share button - opens a dialog instead of popover (popover doesn't work well inside menu)
            rx.box(
                rx.icon(tag="share-2", size=12, color=rx.color("mauve", 9)),
                padding="4px",
                border_radius="4px",
                _hover={"background": rx.color("mauve", 4)},
                on_click=[
                    rx.stop_propagation,
                    lambda: State.open_share_container_dialog(container_id, container_name),
                ],
            ),
            spacing="2",
            width="100%",
        ),
        on_click=lambda: State.select_container(container_id),
    )


def share_container_dialog() -> rx.Component:
    """A dialog for sharing a container with users."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.text("Share Container", font_weight="bold", font_size="16px"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.button(
                            rx.icon(tag="x", size=14),
                            variant="ghost",
                            size="1",
                        ),
                    ),
                    width="100%",
                ),
                rx.text(State.share_dialog_container_name, font_size="14px", color=rx.color("mauve", 9)),
                rx.separator(),
                # Username input section
                rx.box(
                    rx.text("Share with user:", font_size="12px", weight="medium"),
                    rx.hstack(
                        rx.input(
                            placeholder="Username",
                            value=State.share_username_input,
                            on_change=State.set_share_username_input,
                            size="2",
                            style={"width": "200px"},
                        ),
                        rx.button(
                            rx.icon(tag="send", size=12),
                            "Share",
                            size="2",
                            on_click=State.share_container_from_dialog,
                        ),
                        spacing="2",
                    ),
                    width="100%",
                ),
                rx.separator(),
                # Permission level selector
                rx.box(
                    rx.text("Permission:", font_size="12px", weight="medium"),
                    rx.hstack(
                        rx.button(
                            "Read",
                            size="1",
                            variant=rx.cond(State.share_permission == "read", "solid", "outline"),
                            on_click=lambda: State.set_share_permission("read"),
                        ),
                        rx.button(
                            "Write",
                            size="1",
                            variant=rx.cond(State.share_permission == "write", "solid", "outline"),
                            on_click=lambda: State.set_share_permission("write"),
                        ),
                        rx.button(
                            "Admin",
                            size="1",
                            variant=rx.cond(State.share_permission == "admin", "solid", "outline"),
                            on_click=lambda: State.set_share_permission("admin"),
                        ),
                        spacing="1",
                    ),
                    width="100%",
                ),
                rx.separator(),
                # Make public option
                rx.button(
                    rx.hstack(
                        rx.icon(tag="globe", size=14),
                        rx.text("Make public"),
                        spacing="2",
                    ),
                    variant="outline",
                    size="2",
                    width="100%",
                    on_click=State.share_container_public_from_dialog,
                ),
                spacing="3",
                width="300px",
                padding="16px",
            ),
            background_color=rx.color("mauve", 1),
        ),
        open=State.share_container_dialog_open,
        on_open_change=State.set_share_container_dialog_open,
    )


tip_message=rx.vstack(rx.text("Welcome to Finbuddy..."),
rx.text("Create a chat"),
rx.text("and run few commands"),
rx.text("@finbuddy.etf show me some etf on emerging markets")
                      )


def sidebar_chat(chat: str, indent: int = 0) -> rx.Component:
    """A sidebar chat item.

    Args:
        chat: The chat item.
        indent: Indentation level (0 for root, 1 for inside directory, 2 for inside subdirectory)
    """
    return rx.drawer.close(
    rx.button(
        rx.hstack(
            rx.text(chat, width="85%", text_align="left"),
            rx.menu.root(
                rx.menu.trigger(
                    rx.box(
                        rx.icon(tag="menu"),
                        padding_left="0.5em",
                        # Prevent drawer close when clicking menu trigger
                        on_click=rx.stop_propagation,  # Empty handler stops event propagation
                    ),
                ),
                rx.menu.content(
                    rx.menu.item(
                        "Delete",
                        rx.icon(tag="trash", stroke_width=1),
                        color=rx.color("red", 11),
                        on_click=State.delete_chat,
                    ),
                ),
                # Close the menu when clicking outside
                close_on_blur=True,
            ),

            width="100%",
        ),
        rx.cond(
            State.job_ready_chats.contains(chat),
            rx.icon(
                tag="circle",
                color="green",
                size=14,
                style={"borderRadius": "50%", "background": "green", "marginLeft": "0.5em", "cursor": "pointer"},
            ),
            rx.box(width="14px", height="14px", style={"marginLeft": "0.5em", "display": "inline-block"})
        ),
        on_click=lambda: State.set_chat_and_refresh(chat),
        #on_click=lambda: State.set_chat(chat),
        width="100%",
        background_color=rx.color("mauve", 2),
        color=rx.color("mauve", 11),
        padding_left=f"{indent * 1.5}em",
    ),
    # This prevents the drawer from closing when clicking the button
    close_on_overlay_click=False,
)


def sidebar_chat_indented(chat: str) -> rx.Component:
    """A sidebar chat item with indentation for directory contents."""
    return sidebar_chat(chat, indent=1)


def sidebar_chat_double_indented(chat: str) -> rx.Component:
    """A sidebar chat item with double indentation for subdirectory contents."""
    return sidebar_chat(chat, indent=2)


def sidebar_shared_chat_item(shared_chat: Dict[str, Any]) -> rx.Component:
    """A sidebar item for a shared chat (from 'Shared with you' directory).

    Args:
        shared_chat: Dict with chat_id, title, owner, permission
    """
    title = shared_chat["title"]
    owner = shared_chat["owner"]
    permission = shared_chat["permission"]

    # Permission badge color
    permission_color = rx.cond(
        permission == "write",
        "green",
        rx.cond(permission == "admin", "blue", "gray")
    )

    return rx.drawer.close(
        rx.hstack(
            rx.icon(tag="users", size=12, color=rx.color("blue", 9)),
            rx.vstack(
                rx.text(title, font_size="13px", color=rx.color("mauve", 11)),
                rx.hstack(
                    rx.text(f"by {owner}", font_size="10px", color=rx.color("mauve", 8)),
                    rx.badge(permission, color_scheme=permission_color, size="1"),
                    spacing="1",
                ),
                spacing="0",
                align_items="start",
            ),
            width="100%",
            align_items="center",
            spacing="2",
            padding="0.5em",
            padding_left="1.5em",
            cursor="pointer",
            _hover={"backgroundColor": rx.color("mauve", 3)},
            on_click=lambda: State.select_shared_chat(shared_chat),
        ),
    )


def sidebar_shared_with_you_directory(directory: DirectoryInfo) -> rx.Component:
    """Special directory item for 'Shared with you' that displays shared chats from PostgreSQL.

    Args:
        directory: DirectoryInfo with id, name, parent_id, chat_titles keys
    """
    dir_id = directory["id"]
    dir_name = directory["name"]

    return rx.box(
        # Directory header row (clickable to expand/collapse)
        rx.hstack(
            rx.cond(
                State.expanded_dirs.contains(dir_id),
                rx.icon(tag="chevron-down", size=14, color=rx.color("mauve", 9)),
                rx.icon(tag="chevron-right", size=14, color=rx.color("mauve", 9)),
            ),
            rx.cond(
                State.expanded_dirs.contains(dir_id),
                rx.icon(tag="folder-open", size=14, color=rx.color("purple", 9)),
                rx.icon(tag="folder", size=14, color=rx.color("purple", 9)),
            ),
            rx.text(dir_name, font_size="14px", color=rx.color("mauve", 11)),
            # Show count of shared chats
            rx.badge(
                State.shared_chats_list.length(),
                color_scheme="purple",
                size="1",
            ),
            rx.spacer(),
            width="100%",
            align_items="center",
            spacing="2",
            on_click=lambda: State.toggle_directory(dir_id),
            padding="0.5em",
            cursor="pointer",
            _hover={"backgroundColor": rx.color("mauve", 3)},
        ),
        # Expanded content: shared chats from PostgreSQL RBAC
        rx.cond(
            State.expanded_dirs.contains(dir_id),
            rx.box(
                rx.cond(
                    State.shared_chats_list.length() > 0,
                    rx.foreach(
                        State.shared_chats_list,
                        sidebar_shared_chat_item,
                    ),
                    rx.text(
                        "No shared chats",
                        font_size="12px",
                        color=rx.color("mauve", 8),
                        padding_left="2em",
                        padding_y="0.5em",
                    ),
                ),
                width="100%",
            ),
            rx.box(),
        ),
        width="100%",
    )


def sidebar_directory_item(directory: DirectoryInfo) -> rx.Component:
    """A directory item in the sidebar with expand/collapse functionality.

    Args:
        directory: DirectoryInfo with id, name, parent_id, chat_titles keys
    """
    dir_id = directory["id"]
    dir_name = directory["name"]
    chat_titles_var = directory["chat_titles"]

    # Check if this is the "Shared with you" directory
    is_shared_dir = dir_name == "Shared with you"

    return rx.cond(
        is_shared_dir,
        # Special rendering for "Shared with you" directory
        sidebar_shared_with_you_directory(directory),
        # Regular directory rendering
        rx.box(
            # Directory header row (clickable to expand/collapse)
            rx.context_menu.root(
                rx.context_menu.trigger(
                    rx.hstack(
                        rx.cond(
                            State.expanded_dirs.contains(dir_id),
                            rx.icon(tag="chevron-down", size=14, color=rx.color("mauve", 9)),
                            rx.icon(tag="chevron-right", size=14, color=rx.color("mauve", 9)),
                        ),
                        rx.cond(
                            State.expanded_dirs.contains(dir_id),
                            rx.icon(tag="folder-open", size=14, color=rx.color("blue", 9)),
                            rx.icon(tag="folder", size=14, color=rx.color("blue", 9)),
                        ),
                        # Show input when renaming, otherwise show text
                        rx.cond(
                            State.renaming_dir_id == dir_id,
                            rx.input(
                                value=State.rename_dir_value,
                                on_change=State.set_rename_dir_value,
                                on_blur=State.rename_directory_on_blur,
                                on_key_down=State.rename_directory_on_key,
                                size="1",
                                auto_focus=True,
                                style={"width": "100px"},
                            ),
                            rx.text(dir_name, font_size="14px", color=rx.color("mauve", 11)),
                        ),
                        rx.spacer(),
                        width="100%",
                        align_items="center",
                        spacing="2",
                        on_click=lambda: State.toggle_directory(dir_id),
                        on_double_click=lambda: State.start_rename_directory(dir_id),
                        padding="0.5em",
                        cursor="pointer",
                        _hover={"backgroundColor": rx.color("mauve", 3)},
                        # Data attributes for JS drag-drop (drop target)
                        class_name="drop-target-folder",
                        custom_attrs={"data-dir-id": dir_id},
                    ),
                ),
                rx.context_menu.content(
                    rx.context_menu.item(
                        "Rename",
                        on_click=lambda: State.start_rename_directory(dir_id),
                    ),
                    rx.context_menu.item(
                        "New subfolder",
                        on_click=lambda: State.create_directory("New folder", dir_id),
                    ),
                    rx.context_menu.separator(),
                    rx.context_menu.item(
                        "Delete folder",
                        color="red",
                        on_click=lambda: State.delete_directory(dir_id),
                    ),
                ),
            ),
            # Expanded content: chats inside this directory
            rx.cond(
                State.expanded_dirs.contains(dir_id),
                rx.box(
                    rx.foreach(
                        chat_titles_var,
                        sidebar_chat_in_directory,
                    ),
                    width="100%",
                ),
                rx.box(),
            ),
            width="100%",
        ),
    )


def render_move_to_folder_item(folder: Dict) -> rx.Component:
    """Render a single folder menu item for moving a chat."""
    return rx.menu.item(
        rx.hstack(
            rx.icon(tag="folder", size=12),
            rx.text(folder["name"], font_size="12px"),
            spacing="2",
        ),
        on_click=lambda: State.move_current_chat_to_directory(folder["id"]),
    )


def render_share_group_item(group: Dict[str, str]) -> rx.Component:
    """Render a group item in the share submenu."""
    return rx.context_menu.item(
        rx.hstack(
            rx.icon(tag="users", size=12),
            rx.text(group["group_name"], font_size="12px"),
            spacing="2",
        ),
        on_click=lambda: State.share_chat_with_group(group["group_id"], group["group_name"]),
    )


def sidebar_chat_with_menu(chat: str, indent: int = 0, in_directory: bool = False) -> rx.Component:
    """A sidebar chat item with context menu and drag support.

    Args:
        chat: The chat name
        indent: Indentation level
        in_directory: Whether this chat is inside a directory (shows "Move to root" option)
    """
    return rx.drawer.close(
        rx.context_menu.root(
            rx.context_menu.trigger(
                rx.hstack(
                    rx.icon(tag="grip-vertical", size=12, color=rx.color("mauve", 6)),
                    rx.text(chat, width="80%", text_align="left", font_size="14px"),
                    rx.cond(
                        State.job_ready_chats.contains(chat),
                        rx.icon(
                            tag="circle",
                            color="green",
                            size=12,
                            style={"borderRadius": "50%", "background": "green", "marginLeft": "0.5em"},
                        ),
                        rx.box(width="12px", height="12px", style={"marginLeft": "0.5em"}),
                    ),
                    width="100%",
                    align_items="center",
                    spacing="1",
                    on_click=lambda: State.set_chat_and_refresh(chat),
                    padding="0.5em",
                    padding_left=f"{(indent + 1) * 0.75}em",
                    cursor="grab",
                    _hover={"backgroundColor": rx.color("mauve", 3)},
                    # Data attributes for JS drag-drop
                    class_name="draggable-chat",
                    custom_attrs={"data-chat-name": chat, "draggable": "true"},
                ),
            ),
            rx.context_menu.content(
                # Move to root (only if in a directory)
                rx.cond(
                    in_directory,
                    rx.context_menu.item(
                        "Move to root",
                        rx.icon(tag="corner-up-left", size=12),
                        on_click=lambda: State.move_chat_to_directory(chat, None),
                    ),
                    rx.box(),
                ),
                # Share submenu
                rx.context_menu.sub(
                    rx.context_menu.sub_trigger(
                        rx.hstack(
                            rx.icon(tag="share-2", size=12),
                            rx.text("Share", font_size="12px"),
                            spacing="2",
                        ),
                    ),
                    rx.context_menu.sub_content(
                        # Username input section
                        rx.box(
                            rx.text("Share with user:", font_size="11px", color=rx.color("mauve", 9)),
                            rx.hstack(
                                rx.input(
                                    placeholder="Username",
                                    value=State.share_username_input,
                                    on_change=State.set_share_username_input,
                                    size="1",
                                    style={"width": "120px"},
                                ),
                                rx.button(
                                    rx.icon(tag="send", size=10),
                                    size="1",
                                    variant="soft",
                                    on_click=lambda: State.share_chat_with_username_direct(chat),
                                ),
                                spacing="1",
                            ),
                            padding="8px",
                        ),
                        rx.context_menu.separator(),
                        # Permission level selector
                        rx.box(
                            rx.text("Permission:", font_size="11px", color=rx.color("mauve", 9)),
                            rx.hstack(
                                rx.button(
                                    "Read",
                                    size="1",
                                    variant=rx.cond(State.share_permission == "read", "solid", "outline"),
                                    on_click=lambda: State.set_share_permission("read"),
                                ),
                                rx.button(
                                    "Write",
                                    size="1",
                                    variant=rx.cond(State.share_permission == "write", "solid", "outline"),
                                    on_click=lambda: State.set_share_permission("write"),
                                ),
                                rx.button(
                                    "Admin",
                                    size="1",
                                    variant=rx.cond(State.share_permission == "admin", "solid", "outline"),
                                    on_click=lambda: State.set_share_permission("admin"),
                                ),
                                spacing="1",
                            ),
                            padding="8px",
                        ),
                        rx.context_menu.separator(),
                        # Groups section (only show if user has groups)
                        rx.cond(
                            State.user_groups_list.length() > 0,
                            rx.box(
                                rx.text("Share with group:", font_size="11px", color=rx.color("mauve", 9), padding_x="8px"),
                                rx.foreach(
                                    State.user_groups_list,
                                    lambda group: rx.context_menu.item(
                                        rx.hstack(
                                            rx.icon(tag="users", size=12),
                                            rx.text(group["group_name"], font_size="12px"),
                                            spacing="2",
                                        ),
                                        on_click=lambda: State.share_chat_with_group_direct(chat, group["group_id"], group["group_name"]),
                                    ),
                                ),
                            ),
                            rx.box(),
                        ),
                        # Share with all option
                        rx.context_menu.item(
                            rx.hstack(
                                rx.icon(tag="globe", size=12),
                                rx.text("Make public", font_size="12px"),
                                spacing="2",
                            ),
                            on_click=lambda: State.share_chat_public_direct(chat),
                        ),
                    ),
                ),
                rx.context_menu.separator(),
                rx.context_menu.item(
                    "Delete",
                    rx.icon(tag="trash", size=12),
                    color="red",
                    on_click=lambda: State.delete_chat_by_name(chat),
                ),
            ),
        ),
        close_on_overlay_click=False,
    )


def sidebar_chat_in_directory(chat: str) -> rx.Component:
    """A sidebar chat item inside a directory."""
    return sidebar_chat_with_menu(chat, indent=1, in_directory=True)


def sidebar_chat_at_root(chat: str) -> rx.Component:
    """A sidebar chat item at root level."""
    return sidebar_chat_with_menu(chat, indent=0, in_directory=False)


def directory_create_modal(trigger) -> rx.Component:
    """A modal to create a new directory."""
    return rx.dialog.root(
        rx.dialog.trigger(trigger),
        rx.dialog.content(
            rx.vstack(
                rx.heading("New Folder", size="4"),
                rx.input(
                    placeholder="Folder name...",
                    on_blur=State.set_new_dir_name,
                    width="100%",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="soft",
                            color_scheme="gray",
                        ),
                    ),
                    rx.dialog.close(
                        rx.button(
                            "Create",
                            on_click=lambda: State.create_directory(State.new_dir_name),
                        ),
                    ),
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            background_color=rx.color("mauve", 1),
            padding="1.5em",
        ),
    )


def sidebar(trigger) -> rx.Component:
    """The sidebar component."""
    return rx.drawer.root(
        rx.drawer.trigger(trigger),
        rx.drawer.overlay(),
        rx.drawer.portal(
            rx.drawer.content(
                rx.vstack(
                    # Hidden button for drag-drop JS -> Reflex communication
                    rx.el.button(
                        id="drag-drop-trigger",
                        style={"display": "none"},
                        on_click=rx.call_script(
                            "JSON.stringify(window.__dragDropData || {})",
                            callback=State.process_drag_drop_data,
                        ),
                    ),
                    # Drag-drop JavaScript - use rx.script instead of rx.html
                    rx.script(_get_drag_drop_js()),
                    # CSS for drag-drop
                    rx.html(_get_drag_drop_css()),

                    rx.hstack(
                        rx.heading("FinBuddy", size="5", color=rx.color("blue", 11), weight="regular"),
                        rx.drawer.close(
                            rx.button(
                                rx.icon(tag="chevron-left"),
                                width="10%",
                                variant="ghost",
                            )
                        ),

                        sidebar_files(
                            rx.button(
                                rx.icon(
                                    tag="chevron-right",
                                ),
                                width="20%",
                                variant="ghost",
                            )
                        ),
                        # Hstack properties
                        justify="between",  # Puts first item on left, last on right
                        width="100%",  # Takes full available width
                        align_items="center",  # Vertically centers items
                    ),
                    rx.hstack(
                        rx.heading("Workflows", color=rx.color("blue", 11), size="2"),
                        rx.spacer(),
                        # New chat button
                        modal(
                            rx.button(
                                rx.icon(tag="message-square-plus", size=14),
                                variant="ghost",
                                size="1",
                                title="Create new chat",
                            )
                        ),
                        # New folder button
                        directory_create_modal(
                            rx.button(
                                rx.icon(tag="folder-plus", size=14),
                                variant="ghost",
                                size="1",
                                title="Create new folder",
                            )
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.divider(),
                    # Context menu for creating folders via right-click on workflows area
                    rx.context_menu.root(
                        rx.context_menu.trigger(
                            rx.box(
                                # Display directories first
                                rx.foreach(State.root_directories, sidebar_directory_item),
                                # Then display root-level chats
                                rx.foreach(State.root_chats, sidebar_chat_at_root),
                                width="100%",
                                min_height="100px",
                                id="chat-tree-container",
                                class_name="drop-target-root",
                            ),
                        ),
                        rx.context_menu.content(
                            rx.context_menu.item(
                                "New folder",
                                on_click=lambda: State.create_directory("New folder"),
                            ),
                        ),
                    ),
                    align_items="stretch",
                    width="100%",
                ),
                top="auto",
                right="auto",
                height="100%",
                width="20em",
                padding="2em",
                background_color=rx.color("mauve", 2),
                outline="none",
            )
        ),
        direction="left",
    )


def sidebar_files_button(ptf: str) -> rx.Component:
    """A sidebar chat item.

    Args:
        chat: The chat item.
    """
    return rx.drawer.close(rx.hstack(
        rx.button(
            ptf, on_click=lambda: rx.set_value("question", ptf), width="80%",
            variant="surface"
        ),
        rx.button(
            rx.icon(
                tag="area-chart",
                on_click=State.set_statsportfolio(ptf),
                stroke_width=1,
            ),
            width="20%",
            variant="surface",
            color_scheme="red",
        ),
        width="100%",
    ))


def sidebar_files(trigger) -> rx.Component:
    """The sidebar component."""
    return rx.drawer.root(
        rx.drawer.trigger(trigger),
        rx.drawer.overlay(),
        rx.drawer.portal(
            rx.drawer.content(
                rx.vstack(
                    rx.hstack(
                         rx.heading("FinBuddy", size="5", color=rx.color("blue", 11), weight="regular"),
                    # rx.drawer.close(
                    #     rx.link(
                    #         rx.icon("candlestick-chart", style={"color": "white"}),
                    #         href="/stats",
                    #         _hover={"color": "blue"}
                    #     ),
                    #     rx.link(
                    #         rx.icon("gem", style={"color": "white"}),
                    #         href="/holdings",
                    #         _hover={"color": "blue"}
                    #     ),
                    # ),
                        # Hstack properties
                        justify="between",  # Puts first item on left, last on right
                        width="100%",  # Takes full available width
                        align_items="center",  # Vertically centers items
                    ),

                    rx.hstack(rx.heading("Portfolios", color=rx.color("blue", 11), size="2"),
                              rx.button(
                                  rx.icon(
                                      tag="refresh-ccw",
                                  ),
                                  variant="ghost",
                                  on_click=State.set_allportfolios())
                              ),
                    rx.divider(),
                    rx.foreach(State.all_saved_portfolios, lambda ptf: sidebar_files_button(ptf)),
                    align_items="stretch",
                    width="100%",
                ),
                top="auto",
                right="auto",
                height="100%",
                width="25em",
                padding="2em",
                background_color=rx.color("mauve", 2),
                outline="none",
            )
        ),
        direction="left",
    )


def modal(trigger) -> rx.Component:
    """A modal to create a new chat."""
    return rx.dialog.root(
        rx.dialog.trigger(trigger),
        rx.dialog.content(
            rx.hstack(
                rx.input(
                    placeholder="Workflow name...",
                    on_blur=State.set_new_chat_name,
                    width=["15em", "20em", "30em", "30em", "30em", "30em"],
                ),
                rx.dialog.close(
                    rx.button(
                        "New workflow",
                        on_click=State.create_chat,
                    ),
                ),
                background_color=rx.color("mauve", 1),
                spacing="2",
                width="100%",
            ),
        ),
    )


def navbar():
    return rx.fragment(
    rx.box(
        rx.hstack(
            rx.hstack(
                #rx.avatar(fallback="FB", variant="solid"),
                rx.menu.root(
                    rx.menu.trigger(
                        rx.button(
                            "",
                            rx.icon(tag="chevron_down", weight=16, height=10),
                            # font_family=FONT_FAMILY,
                            variant="soft",
                        ),
                    ),
                    rx.menu.content(
                        rx.menu.item("Markets", shortcut="⌘ M", on_select=State.handle_redirect_markets()),
                        rx.menu.item("Chat", shortcut="⌘ C", on_select=rx.redirect("/")),
                        rx.menu.item("Portfolio Dashboard", shortcut="⌘ P", on_select=rx.redirect("/stats")),
                        #rx.menu.item("Plots", shortcut="⌘ P", on_select=rx.redirect("/plots")),
                        rx.menu.item("Community", disabled=True),
                        rx.menu.item("Live trading", shortcut="⌘ L", on_select=rx.redirect("/live"), disabled=False),
                        # font_family=FONT_FAMILY,
                        variant="soft",

                    ),
                    variant="soft",
                    # font_family=FONT_FAMILY,

                ),
                # rx.desktop_only(
                #     rx.badge(
                #         State.current_chat,
                #         rx.tooltip(rx.icon("info", size=9), content="The current selected chat."),
                #         variant="soft",
                #         color=rx.color("mauve", 6)
                #     )
                # ),

                rx.desktop_only(
                    rx.button(
                        rx.icon(
                            tag="info",
                            color=rx.color("mauve", 6),
                            on_click=rx.redirect("/exchange"),
                            size=20
                        ),
                        background_color=rx.color("blue", 12),
                    )
                ),

                # Container selector - Message routing switch and Agents dropdown
                # Only visible on the main chat page (index)
                rx.cond(
                    State.is_chat_page,
                    rx.hstack(
                        # Vertical divider before Finbuddy
                        rx.box(
                            width="1px",
                            height="20px",
                            background="rgba(255,255,255,0.3)",
                            margin_x="8px",
                        ),

                    # Finbuddy label
                    rx.text("Finbuddy", font_size="11px", color="white", white_space="nowrap"),

                    # 3-position routing switch
                    # Left = Finbuddy (blue), Center = Comment (gray), Right = Agent (green)
                    rx.box(
                        # Track background
                        rx.box(
                            # Sliding knob with link icon
                            rx.box(
                                rx.icon(
                                    tag="link",
                                    size=12,
                                    color="white",
                                ),
                                position="absolute",
                                width="20px",
                                height="20px",
                                border_radius="50%",
                                display="flex",
                                align_items="center",
                                justify_content="center",
                                transition="all 0.2s ease",
                                # Position based on routing mode
                                left=rx.cond(
                                    State.routing_is_finbuddy,
                                    "2px",  # Left position
                                    rx.cond(
                                        State.routing_is_comment,
                                        "22px",  # Center position
                                        "42px",  # Right position (agent)
                                    ),
                                ),
                                top="2px",
                                # Color based on routing mode
                                background=rx.cond(
                                    State.routing_is_finbuddy,
                                    "#3b82f6",  # Blue for Finbuddy
                                    rx.cond(
                                        State.routing_is_comment,
                                        "#6b7280",  # Gray for Comment
                                        "#22c55e",  # Green for Agent
                                    ),
                                ),
                            ),
                            position="relative",
                            width="64px",
                            height="24px",
                            background="rgba(255,255,255,0.2)",
                            border_radius="12px",
                        ),
                        # Clickable areas for the 3 positions
                        rx.hstack(
                            # Left click area (Finbuddy)
                            rx.box(
                                width="21px",
                                height="24px",
                                cursor="pointer",
                                on_click=lambda: State.set_message_routing("finbuddy"),
                            ),
                            # Center click area (Comment)
                            rx.box(
                                width="22px",
                                height="24px",
                                cursor="pointer",
                                on_click=lambda: State.set_message_routing("comment"),
                            ),
                            # Right click area (Agent)
                            rx.box(
                                width="21px",
                                height="24px",
                                cursor="pointer",
                                on_click=lambda: State.set_message_routing("agent"),
                            ),
                            position="absolute",
                            top="0",
                            left="0",
                            spacing="0",
                        ),
                        position="relative",
                        title=rx.cond(
                            State.routing_is_finbuddy,
                            "Finbuddy mode: Messages sent to backend",
                            rx.cond(
                                State.routing_is_comment,
                                "Comment mode: Messages saved locally only",
                                "Agent mode: Messages sent to selected agent",
                            ),
                        ),
                    ),

                    # Agents dropdown menu
                    rx.menu.root(
                        rx.menu.trigger(
                            rx.button(
                                rx.icon(tag="container", size=16, color="white"),
                                rx.text("Agents", font_size="12px", color="white"),
                                rx.icon(tag="chevron_down", size=12, color="white"),
                                variant="ghost",
                                size="1",
                            ),
                        ),
                        rx.menu.content(
                            rx.cond(
                                State.has_running_containers,
                                rx.foreach(
                                    State.running_containers,
                                    render_container_menu_item,
                                ),
                                rx.menu.item(
                                    rx.text("No running containers", font_size="12px", color=rx.color("mauve", 9)),
                                    disabled=True,
                                ),
                            ),
                            variant="soft",
                        ),
                        on_open_change=State.load_running_containers,
                    ),

                    # Selected container name badge (only visible when container selected)
                    rx.cond(
                        State.selected_container_id != "",
                        rx.badge(
                            State.selected_container_name,
                            rx.button(
                                rx.icon(tag="x", size=10),
                                variant="ghost",
                                size="1",
                                padding="0",
                                on_click=State.clear_container_selection,
                            ),
                            variant="soft",
                            color_scheme="green",
                            size="1",
                        ),
                        rx.box(),  # Empty box when no container selected
                    ),

                    # Divider between agent and page view toggle
                    rx.box(
                        width="1px",
                        height="20px",
                        background="rgba(255,255,255,0.3)",
                        margin_x="8px",
                    ),

                    # Page view toggle switch
                    rx.hstack(
                        rx.text("Chat", font_size="11px", color="white"),
                        rx.switch(
                            checked=State.show_page_view,
                            on_change=State.toggle_page_view,
                            size="1",
                        ),
                        rx.text("GUI", font_size="11px", color="white"),
                        spacing="1",
                        align_items="center",
                    ),

                    # Session ID display and New Session button (only visible when agent selected)
                    rx.cond(
                        State.selected_container_id != "",
                        rx.hstack(
                            # Divider
                            rx.box(
                                width="1px",
                                height="20px",
                                background="rgba(255,255,255,0.3)",
                                margin_x="8px",
                            ),
                            # Session selector - dropdown if multiple sessions, badge if single
                            rx.cond(
                                State.available_sessions.length() > 1,
                                # Multiple sessions - show dropdown menu
                                rx.menu.root(
                                    rx.menu.trigger(
                                        rx.button(
                                            rx.hstack(
                                                rx.text("Session: ", font_size="9px", color="white"),
                                                rx.text(
                                                    State.current_session_id,
                                                    font_size="9px",
                                                    color="white",
                                                    max_width="60px",
                                                    overflow="hidden",
                                                    text_overflow="ellipsis",
                                                    white_space="nowrap",
                                                ),
                                                rx.icon(tag="chevron-down", size=10, color="white"),
                                                spacing="1",
                                                align_items="center",
                                            ),
                                            variant="soft",
                                            size="1",
                                            color_scheme="blue",
                                        ),
                                    ),
                                    rx.menu.content(
                                        rx.foreach(
                                            State.available_sessions,
                                            lambda session: rx.menu.item(
                                                rx.hstack(
                                                    rx.cond(
                                                        State.current_session_id == session["session_id"],
                                                        rx.icon(tag="check", size=12, color="green"),
                                                        rx.box(width="12px"),
                                                    ),
                                                    rx.vstack(
                                                        rx.text(
                                                            session["session_id"],
                                                            font_size="10px",
                                                            font_family="monospace",
                                                            max_width="200px",
                                                            overflow="hidden",
                                                            text_overflow="ellipsis",
                                                        ),
                                                        rx.text(
                                                            session["created_at"],
                                                            font_size="8px",
                                                            color="#6b7280",
                                                        ),
                                                        spacing="0",
                                                        align_items="start",
                                                    ),
                                                    spacing="2",
                                                    align_items="center",
                                                ),
                                                on_click=lambda s=session: State.select_session(s["session_id"]),
                                            ),
                                        ),
                                    ),
                                ),
                                # Single or no session - show simple badge
                                rx.badge(
                                    rx.text("Session: ", font_size="9px"),
                                    rx.text(
                                        State.current_session_id,
                                        font_size="9px",
                                        max_width="60px",
                                        overflow="hidden",
                                        text_overflow="ellipsis",
                                        white_space="nowrap",
                                    ),
                                    variant="soft",
                                    color_scheme="blue",
                                    size="1",
                                ),
                            ),
                            # New Session button
                            rx.button(
                                rx.icon(tag="plus", size=12),
                                rx.text("New", font_size="10px"),
                                variant="soft",
                                size="1",
                                on_click=State.create_new_agent_session,
                                title="Create a new session for this agent",
                            ),
                            spacing="2",
                            align_items="center",
                        ),
                        rx.box(),  # Empty box when no agent selected
                    ),

                    spacing="2",
                    align_items="center",
                    margin_left="1em",
                ),
                    rx.box(),  # Empty box when not on chat page
                ),  # End of rx.cond for is_chat_page

                #rx.theme_panel(),

                # rx.dialog.root(
                #     rx.dialog.trigger(rx.button("Help", background_color="#092b57", font_size="9px",)),
                #     rx.dialog.content(
                #         rx.dialog.title("FinBuddy_v0"),
                #         rx.dialog.description(
                #             tip_message,
                #         ),
                #         rx.dialog.close(
                #             rx.button("Go explore", size="3"),
                #         ),
                #     ),
                # ),


                align_items="center",
            ),
            # rx.hstack(
            #     rx.progress(value=State.value),
            #     width="6%",
            #     on_click=State.start_progress
            # ),
            rx.spacer(),
            rx.hstack(
                # News feed bell with notifications
                news_feed_bell(),
                # Logout button
                rx.button(rx.icon(tag="circle-power"),
                          variant="ghost",
                          on_click=State.logout(),
                          margin="0",  # Remove default margins
                          ),
                spacing="2",
                align_items="center",
            ),
            # rx.hstack(
            #
            #     sidebar_files(
            #         rx.button(
            #             rx.icon(
            #                 tag="zoom_in",
            #                 color=rx.color("white", 5),
            #                 size=20
            #             ),
            #             background_color=rx.color("blue", 12),
            #         )
            #     ),
            #     sidebar(
            #         rx.button(
            #             rx.icon(
            #                 tag="messages-square",
            #                 color=rx.color("white", 5),
            #                 size=20
            #             ),
            #             background_color=rx.color("blue", 12),
            #
            #         )
            #     ),
            #
            #     align_items="center",
            # ),
            justify_content="space-between",
            align_items="center",
            position="sticky",
            padding="12px",
            width="100%",
        ),
        # Tab bar - only visible on chat page
        rx.cond(
            State.is_chat_page,
            rx.hstack(
                # New tab bar
                rx.foreach(State.tabs_list, lambda tab: rx.hstack(
                    rx.text(tab,
                        background_color=rx.cond(  # Change background if active
                        tab == State.active_tab,
                        "white",  # Active tab color
                        rx.color("mauve", 2),  # Inactive tab color
                        ),  # Set background to light gray
                        color=rx.color("blue", 10),
                        margin="0",  # Remove any margin
                        padding="0",
                        padding_left="1em",
                        padding_top="0.5em",
                        width="auto",
                        height="2em",
                        on_click=lambda: State.set_chat(tab)
                        ),
                    rx.button("x",
                        background_color=rx.cond(
                            tab == State.active_tab,
                            "white",
                            rx.color("mauve", 2),
                        ),
                        color=rx.color("blue", 10),
                        visibility=rx.cond(
                            tab == State.active_tab,
                            "visible",
                            "hidden",
                        ),
                        _hover={
                            "background_color": rx.color("mauve", 5),  # Change bg on hover                      # Change 'x' color
                            # Optional: Add border
                        },
                        padding_top="0.5em",  # Add top padding equivalent to half a character
                    padding_bottom="0.5em",  # Add bottom padding equivalent to half a character
                    width="1em",
                    on_click=lambda: State.close_tab(tab)
                ),
                    margin="0",  # Remove any margin
                    padding="0",  # Remove any padding
                    justify_content="flex-start",
                    align_items="center",
                    width="auto",
                    background_color=rx.cond(  # Match button bg to tab state
                        tab == State.active_tab,
                    "white",
                    rx.color("mauve", 2),
                    ), # rx.color("blue", 12) if State.active_tab == tab else rx.color("white", 1),
                    _hover={
                "button": {
                    "visibility": "visible"
                }
            },

                )
            ),
                rx.spacer(),
                justify_content="flex-start",
                align_items="center",
                width="100%",
                height="auto",
                #padding="2px",
                border_top=f"1px solid {rx.color('mauve', 3)}",
                background_color=rx.color("mauve", 2),
                z_index="1010",
            ),
            rx.box(),  # Empty box when not on chat page
        ),
        direction="column",
        spacing="0",
        backdrop_filter="auto",
        backdrop_blur="lg",
        #padding="12px",
        #border_bottom=f"1px solid {rx.color('mauve', 3)}",
        background_color=rx.color("blue", 12),
        position="sticky",
        top="0",
        z_index="1000"
    ),
    # Share container dialog (rendered at page level)
    share_container_dialog(),
    )


def thin_sidebar() -> rx.Component:
    """The persistent thin sidebar with menu button."""
    return rx.box(
        rx.vstack(

            # Logo at the top of the sidebar
            rx.image(
                src="/finbuddy_logo.png",
                width="40px",
                height="40px",
                style={"marginTop": "0em", "marginBottom": "1em"},
                alt="Finbuddy Logo"
            ),

            # Menu button to expand the full sidebar - now properly connected

            sidebar(
                rx.button(
                    rx.icon(tag="chevron-right"),
                    width="100%",
                    variant="ghost",
                    margin="0",  # Remove default margins
                )
            ),
            # Chat button - opens current chat (same as Chat menu item)
            rx.button(
                rx.icon(tag="message-square"),
                variant="ghost",
                width="100%",
                margin="0",
                on_click=lambda: rx.redirect("/"),
            ),
            # New chat button with modal
            modal(rx.button(
                rx.icon(
                    tag="message-square-plus",
                ),
                variant="ghost",
                width="100%",
                margin="0",  # Remove default margins
            )
            ),
            # Divider after new chat button
            rx.divider(width="80%", margin_y="0.5em"),
            # Stats button
            rx.button(
                rx.icon(tag="line-chart"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.75em",
                on_click=lambda: rx.redirect("/stats"),
            ),
            # Markets button
            rx.button(
                rx.icon(tag="bar-chart"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.5em",
                on_click=State.handle_redirect_markets,
            ),
            # Holdings button
            rx.button(
                rx.icon(tag="gem"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.5em",
                on_click=lambda: rx.redirect("/holdings"),
            ),
            # Divider before agent builder section
            rx.divider(width="80%", margin_y="0.5em"),
            # Agent button
            rx.button(
                rx.icon(tag="bot"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.5em",
                on_click=lambda: rx.redirect("/agent"),
            ),
            # Data Onboarding button
            rx.button(
                rx.icon(tag="database"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.5em",
                on_click=lambda: rx.redirect("/data_onboarding"),
            ),
            # Page Builder button
            rx.button(
                rx.icon(tag="layout_dashboard"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.5em",
                on_click=lambda: rx.redirect("/page_builder"),
            ),
            # Divider before notifications
            rx.divider(width="80%", margin_y="0.5em"),
            # Notifications button
            rx.button(
                rx.icon(tag="bell"),
                variant="ghost",
                width="100%",
                margin="0",
                on_click=lambda: rx.redirect("/notifications"),
            ),
            # Agents Management button
            rx.button(
                rx.icon(tag="cpu"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.5em",
                on_click=lambda: rx.redirect("/agents_management"),
            ),
            # MCP Discovery Search button
            rx.button(
                rx.icon(tag="search"),
                variant="ghost",
                width="100%",
                margin="0",
                margin_top="0.5em",
                on_click=lambda: rx.redirect("/mcp_search"),
            ),
            # Divider before settings
            rx.divider(width="80%", margin_y="0.5em"),
            # Settings button
            rx.button(
                rx.icon(tag="settings"),
                variant="ghost",
                width="100%",
                margin="0",
                on_click=lambda: rx.redirect("/settings"),
            ),
            # Spacer to push content
            rx.spacer(),

            #Add other sidebar icons here

                # sidebar_files(
                #     rx.button(
                #         rx.icon(
                #             tag="file-code-2",
                #         ),
                #         variant="ghost",
                #         width="100%",
                #         background_color=rx.color("white", 1),
                #     )
                # ),
                # sidebar(
                #     rx.button(
                #         rx.icon(
                #             tag="messages-square",
                #         ),
                #         variant="ghost",
                #         width="100%",
                #     )
                # ),
            spacing="3",
            height="100vh",
            align_items="center",
            padding_top="1em",
            padding_bottom="3em",
        ),
        width="60px",
        height="100vh",
        position="fixed",
        left="0",
        top="0",
        border_right="1px solid #eee",
        background_color=rx.color("white", 1),
        z_index="1010",
        overflow="hidden",  # Prevent content from overflowing
    )


def _get_drag_drop_css() -> str:
    """Return the CSS for drag-and-drop styling."""
    return """
<style>
.draggable-chat.dragging {
    opacity: 0.5;
}
.drop-target-folder.drag-over {
    background-color: rgba(59, 130, 246, 0.2) !important;
    outline: 2px dashed #3b82f6;
    border-radius: 4px;
}
.drop-target-root.drag-over {
    background-color: rgba(59, 130, 246, 0.1) !important;
}
</style>
"""


def _get_drag_drop_js() -> str:
    """Return the JavaScript for drag-and-drop functionality."""
    return """
console.log('[DRAG-DROP JS] Script loaded');

(function() {
    let draggedChatName = null;

    // Check if already initialized on this specific container
    function isContainerInitialized(container) {
        return container && container.dataset.dragDropInit === 'true';
    }

    function initDragDrop() {
        console.log('[DRAG-DROP JS] initDragDrop called');

        const container = document.getElementById('chat-tree-container');
        if (!container) {
            console.log('[DRAG-DROP JS] Container not found yet');
            return false;
        }

        if (isContainerInitialized(container)) {
            console.log('[DRAG-DROP JS] Already initialized on this container');
            return true;
        }

        // Mark as initialized
        container.dataset.dragDropInit = 'true';
        console.log('[DRAG-DROP JS] Initializing on container');

        // Use event delegation on the container
        container.addEventListener('dragstart', function(e) {
            const chatItem = e.target.closest('.draggable-chat');
            if (chatItem) {
                draggedChatName = chatItem.getAttribute('data-chat-name');
                chatItem.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', draggedChatName);
                console.log('[DRAG-DROP JS] Started dragging:', draggedChatName);
            }
        });

        container.addEventListener('dragend', function(e) {
            const chatItem = e.target.closest('.draggable-chat');
            if (chatItem) {
                chatItem.classList.remove('dragging');
            }
            draggedChatName = null;
            // Remove all drag-over states
            document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        });

        container.addEventListener('dragover', function(e) {
            if (!draggedChatName) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            // Highlight folder targets
            const folder = e.target.closest('.drop-target-folder');
            if (folder) {
                // Remove from other folders
                document.querySelectorAll('.drop-target-folder.drag-over').forEach(el => {
                    if (el !== folder) el.classList.remove('drag-over');
                });
                folder.classList.add('drag-over');
            }
        });

        container.addEventListener('dragleave', function(e) {
            const folder = e.target.closest('.drop-target-folder');
            if (folder && !folder.contains(e.relatedTarget)) {
                folder.classList.remove('drag-over');
            }
        });

        container.addEventListener('drop', function(e) {
            e.preventDefault();
            if (!draggedChatName) return;

            const folder = e.target.closest('.drop-target-folder');
            let dirId = null;

            if (folder) {
                dirId = folder.getAttribute('data-dir-id');
                folder.classList.remove('drag-over');
            }

            console.log('[DRAG-DROP JS] Drop detected. Chat:', draggedChatName, 'Dir:', dirId);

            // Trigger the Reflex event
            triggerMoveChat(draggedChatName, dirId);
            draggedChatName = null;
        });

        console.log('[DRAG-DROP JS] Initialized successfully');
        return true;
    }

    function triggerMoveChat(chatName, dirId) {
        console.log('[DRAG-DROP JS] Triggering move. Chat:', chatName, 'Dir:', dirId);

        // Store data in window for Reflex to pick up
        window.__dragDropData = { chat: chatName, dir_id: dirId };

        // Find and click the hidden trigger button
        const triggerBtn = document.getElementById('drag-drop-trigger');
        if (triggerBtn) {
            console.log('[DRAG-DROP JS] Clicking trigger button');
            triggerBtn.click();
        } else {
            console.log('[DRAG-DROP JS] ERROR: Trigger button not found');
        }
    }

    // Try to initialize immediately
    initDragDrop();

    // Also try after a short delay (drawer animation)
    setTimeout(initDragDrop, 100);
    setTimeout(initDragDrop, 500);
})();
"""
