"""The authentication state."""
import reflex as rx
from sqlmodel import select

from finbuddy.state import State, User, Chats, bot
from finbuddy.data_models.db_users import QA, DataPlot, DataTable, Portfolio, Portfolios, ChatDirectory

from YourIndexingAI.rx_interface import add_user
import copy

# JWT token generation and PostgreSQL user sync
from db_light.auth.jwt_utils import create_access_token, verify_google_token
from db_light.auth.auth_db import ensure_user_exists

# Email verification imports
from finbuddy.utils.email_sender import send_verification_email, validate_email_format
from db_light.auth.verification_service import (
    create_pending_verification,
    verify_code as verify_email_code,
    check_email_available
)

# Password hashing utilities
from finbuddy.utils.password_utils import hash_password, verify_password, needs_rehash


def popup_aware_redirect(destination: str, success: bool = True, error: str = "") -> rx.Component:
    """
    Redirect that's aware of popup context.

    If in a popup window (from OAuth), sends postMessage to opener and closes.
    If in main window, does normal redirect.

    Args:
        destination: URL to redirect to (e.g., "/" or "/login")
        success: Whether the operation was successful
        error: Error message if not successful
    """
    error_escaped = error.replace("'", "\\'").replace('"', '\\"')
    script = f"""
        if (window.opener && !window.opener.closed) {{
            // We're in a popup - notify parent and close
            window.opener.postMessage({{
                type: 'oauth_callback',
                success: {'true' if success else 'false'},
                error: '{error_escaped}'
            }}, window.location.origin);
            window.close();
        }} else {{
            // Normal window - do regular redirect
            window.location.href = '{destination}';
        }}
    """
    return rx.call_script(script)


def popup_aware_error(error_message: str) -> rx.Component:
    """
    Show error that's aware of popup context.

    If in a popup window (from OAuth), sends error postMessage to opener and closes.
    If in main window, shows alert and redirects to login.

    Args:
        error_message: Error message to display
    """
    error_escaped = error_message.replace("'", "\\'").replace('"', '\\"')
    script = f"""
        if (window.opener && !window.opener.closed) {{
            // We're in a popup - notify parent of error and close
            window.opener.postMessage({{
                type: 'oauth_callback',
                success: false,
                error: '{error_escaped}'
            }}, window.location.origin);
            window.close();
        }} else {{
            // Normal window - show alert and redirect to login
            alert('{error_escaped}');
            window.location.href = '/login';
        }}
    """
    return rx.call_script(script)


class AuthState(State):
    """The authentication state for sign up and login page."""

    username: str
    password: str
    confirm_password: str
    google_id_token: str = ""  # Token received from Google OAuth flow

    # Email verification state
    email: str = ""
    verification_code: str = ""
    signup_step: int = 1  # 1 = enter email, 2 = enter code + credentials
    signup_error: str = ""  # Error message to display
    signup_loading: bool = False  # Loading state for async operations

    # Username availability state
    username_checked: bool = False  # Whether username has been checked
    username_available: bool = False  # Whether current username is available
    username_check_message: str = ""  # Message to display (available/taken)

    # Password reset state
    reset_email: str = ""  # Email for password reset
    reset_code: str = ""  # Verification code for reset
    reset_new_password: str = ""  # New password
    reset_confirm_password: str = ""  # Confirm new password
    reset_step: int = 1  # 1 = enter email, 2 = enter code + new password
    reset_error: str = ""  # Error message to display
    reset_loading: bool = False  # Loading state for async operations

    # Terms acceptance state
    terms_accepted: bool = False  # Whether user has accepted terms during signup


    def signup(self):
        """Sign up a user."""
        with rx.session() as session:
            session.expire_on_commit = False
            if self.password != self.confirm_password:
                return rx.window_alert("Passwords do not match.")
            if session.exec(select(User).where(User.username == self.username)).first():
                return rx.window_alert("Username already exists.")
            # Hash the password before storing
            hashed_pw = hash_password(self.password)
            new_user = User(username=self.username, password=hashed_pw)
            self.user = new_user
            session.add(new_user)
            session.commit()  # Commit to get the user ID
            session.refresh(self.user)
            default_chat = Chats(chat_title="Buddy", user_id=self.user.id)
            session.add(default_chat)
            created=add_user(self.user.username)
            #TODO handle errros

            # Create user in PostgreSQL RBAC database for permissions
            ensure_user_exists(user_id=self.user.username)

            # Create default "Shared with you" directory for shared chats
            shared_dir = ChatDirectory(
                user_id=self.user.id,
                name="Shared with you",
                parent_id=None,
                order=9999  # High order to appear at the bottom
            )
            session.add(shared_dir)

            session.commit()

            # Generate JWT token for API authentication
            self.jwt_token = create_access_token(user_id=self.user.username)

            self.current_chat="Buddy"
            self.chats_list = {
                        "Buddy": [],
                        }
            self.chats_name_plots = {
                        "Buddy": [],
                        }
            self.chats_name_tables = {
                        "Buddy": [],
                        }
            self.chats_name_portfolios = {
                        "Buddy": [],
                        }
            self.chats_data_plots = {
                        "Buddy": [],
                        }
            self.chats_data_tables = {
                "Buddy": [],
            }

            # Load chat directories for the tree view (includes the new "Shared with you" dir)
            self.load_directories_from_db()

            # Load user's groups for sharing functionality (will be empty for new user)
            self.get_user_groups_list()

            return rx.redirect("/")

    def send_verification(self):
        """
        Step 1 of email verification signup.
        Validate email, create pending verification, and send code.
        """
        self.signup_error = ""
        self.signup_loading = True

        # Validate email format
        if not self.email or not validate_email_format(self.email):
            self.signup_error = "Please enter a valid email address."
            self.signup_loading = False
            return

        email = self.email.lower().strip()

        # Check if email is already registered in Reflex DB
        with rx.session() as session:
            existing_user = session.exec(
                select(User).where(User.email == email)
            ).first()
            if existing_user:
                self.signup_error = "This email is already registered. Please sign in."
                self.signup_loading = False
                return

        # Create pending verification and get code
        success, result, error_type = create_pending_verification(email)

        if not success:
            self.signup_error = result
            self.signup_loading = False
            return

        # Send verification email
        code = result
        email_sent, email_error = send_verification_email(email, code)

        if not email_sent:
            self.signup_error = f"Failed to send verification email: {email_error}"
            self.signup_loading = False
            return

        # Move to step 2
        self.signup_step = 2
        self.signup_loading = False
        print(f"[AuthState] Verification code sent to {email}", flush=True)

    def resend_verification(self):
        """Resend verification code to the current email."""
        self.signup_error = ""
        self.signup_loading = True

        if not self.email:
            self.signup_error = "No email address to send to."
            self.signup_loading = False
            return

        email = self.email.lower().strip()

        # Create new pending verification
        success, result, error_type = create_pending_verification(email)

        if not success:
            self.signup_error = result
            self.signup_loading = False
            return

        # Send verification email
        code = result
        email_sent, email_error = send_verification_email(email, code)

        if not email_sent:
            self.signup_error = f"Failed to send verification email: {email_error}"
            self.signup_loading = False
            return

        self.signup_error = ""  # Clear any previous error
        self.signup_loading = False
        print(f"[AuthState] Verification code resent to {email}", flush=True)
        return rx.window_alert("Verification code sent! Please check your email.")

    def complete_signup(self):
        """
        Step 2 of email verification signup.
        Verify code and create user account.
        """
        self.signup_error = ""
        self.signup_loading = True

        # Validate inputs
        if not self.verification_code:
            self.signup_error = "Please enter the verification code."
            self.signup_loading = False
            return

        if not self.username:
            self.signup_error = "Please enter a username."
            self.signup_loading = False
            return

        if not self.password:
            self.signup_error = "Please enter a password."
            self.signup_loading = False
            return

        if self.password != self.confirm_password:
            self.signup_error = "Passwords do not match."
            self.signup_loading = False
            return

        # Validate terms acceptance
        if not self.terms_accepted:
            self.signup_error = "You must accept the Terms of Service and Disclaimer to create an account."
            self.signup_loading = False
            return

        email = self.email.lower().strip()

        # If username hasn't been checked, do the check now
        if not self.username_checked:
            self.check_username_availability()
            # If username was changed (not available), stop and let user review
            if not self.username_available:
                self.signup_error = "Please review the suggested username and click Check again."
                self.signup_loading = False
                return

        # If username was checked but not available (shouldn't happen, but safety check)
        if not self.username_available:
            self.signup_error = "Please check username availability first."
            self.signup_loading = False
            return

        # Verify the code
        code_valid, code_error = verify_email_code(email, self.verification_code.strip())

        if not code_valid:
            self.signup_error = code_error
            self.signup_loading = False
            return

        # Code is valid - create the user account
        with rx.session() as session:
            session.expire_on_commit = False

            # Double-check username availability (in case of race condition)
            if session.exec(select(User).where(User.username == self.username)).first():
                self.signup_error = "Username was just taken. Please choose another."
                self.username_checked = False
                self.username_available = False
                self.signup_loading = False
                return

            # Check email again (in case of race condition)
            if session.exec(select(User).where(User.email == email)).first():
                self.signup_error = "Email already registered."
                self.signup_loading = False
                return

            # Create user with email (hash the password)
            # Include terms acceptance timestamp and version
            import time
            hashed_pw = hash_password(self.password)
            new_user = User(
                username=self.username,
                email=email,
                password=hashed_pw,
                terms_accepted_at=time.time(),
                terms_version="2025-01"  # Update this when terms change
            )
            self.user = new_user
            session.add(new_user)
            session.commit()
            session.refresh(self.user)

            # Create default chat
            default_chat = Chats(chat_title="Buddy", user_id=self.user.id)
            session.add(default_chat)

            # Add to indexing system
            created = add_user(self.user.username)

            # Create user in PostgreSQL RBAC database for permissions
            ensure_user_exists(user_id=self.user.username)

            # Create default "Shared with you" directory for shared chats
            shared_dir = ChatDirectory(
                user_id=self.user.id,
                name="Shared with you",
                parent_id=None,
                order=9999
            )
            session.add(shared_dir)
            session.commit()

            # Generate JWT token for API authentication
            self.jwt_token = create_access_token(user_id=self.user.username)

            # Initialize chat structures
            self.current_chat = "Buddy"
            self.chats_list = {"Buddy": []}
            self.chats_name_plots = {"Buddy": []}
            self.chats_name_tables = {"Buddy": []}
            self.chats_name_portfolios = {"Buddy": []}
            self.chats_data_plots = {"Buddy": []}
            self.chats_data_tables = {"Buddy": []}

            # Load chat directories for the tree view
            self.load_directories_from_db()

            # Load user's groups for sharing functionality
            self.get_user_groups_list()

            # Reset signup state
            self.signup_step = 1
            self.signup_error = ""
            self.signup_loading = False
            self.email = ""
            self.verification_code = ""
            self.terms_accepted = False

            print(f"[AuthState] User {self.username} created successfully with verified email {email}", flush=True)

            return rx.redirect("/")

    def go_back_to_email(self):
        """Go back to step 1 (email entry) from step 2."""
        self.signup_step = 1
        self.signup_error = ""
        self.verification_code = ""
        self.terms_accepted = False

    def check_username_availability(self):
        """
        Check if the current username is available.
        If not, suggest an alternative with random digits.
        """
        import secrets

        if not self.username or len(self.username.strip()) < 3:
            self.username_check_message = "Username must be at least 3 characters."
            self.username_checked = False
            self.username_available = False
            return

        username = self.username.strip()

        with rx.session() as session:
            existing = session.exec(
                select(User).where(User.username == username)
            ).first()

            if existing:
                # Username taken - suggest alternative
                random_suffix = ''.join([str(secrets.randbelow(10)) for _ in range(3)])
                suggested = f"{username}_{random_suffix}"
                self.username = suggested
                self.username_check_message = f"Username taken. Suggested: {suggested}"
                self.username_checked = True
                self.username_available = False
                # Recursively check the suggested username
                self.check_username_availability()
            else:
                self.username_check_message = "Username is available!"
                self.username_checked = True
                self.username_available = True

    def reset_username_check(self):
        """Reset username check state when username is modified."""
        self.username_checked = False
        self.username_available = False
        self.username_check_message = ""

    # ==================== PASSWORD RESET METHODS ====================

    def send_reset_code(self):
        """
        Step 1 of password reset.
        Validate email exists and send verification code.
        """
        self.reset_error = ""
        self.reset_loading = True

        # Validate email format
        if not self.reset_email or not validate_email_format(self.reset_email):
            self.reset_error = "Please enter a valid email address."
            self.reset_loading = False
            return

        email = self.reset_email.lower().strip()

        # Check if email exists in Reflex DB
        with rx.session() as session:
            existing_user = session.exec(
                select(User).where(User.email == email)
            ).first()
            if not existing_user:
                self.reset_error = "No account found with this email address."
                self.reset_loading = False
                return

        # Create pending verification and get code (reuses signup verification)
        success, result, error_type = create_pending_verification(email)

        if not success:
            self.reset_error = result
            self.reset_loading = False
            return

        # Send verification email
        code = result
        email_sent, email_error = send_verification_email(email, code)

        if not email_sent:
            self.reset_error = f"Failed to send verification email: {email_error}"
            self.reset_loading = False
            return

        # Move to step 2
        self.reset_step = 2
        self.reset_loading = False
        print(f"[AuthState] Password reset code sent to {email}", flush=True)

    def resend_reset_code(self):
        """Resend password reset verification code."""
        self.reset_error = ""
        self.reset_loading = True

        if not self.reset_email:
            self.reset_error = "No email address to send to."
            self.reset_loading = False
            return

        email = self.reset_email.lower().strip()

        # Create new pending verification
        success, result, error_type = create_pending_verification(email)

        if not success:
            self.reset_error = result
            self.reset_loading = False
            return

        # Send verification email
        code = result
        email_sent, email_error = send_verification_email(email, code)

        if not email_sent:
            self.reset_error = f"Failed to send verification email: {email_error}"
            self.reset_loading = False
            return

        self.reset_error = ""
        self.reset_loading = False
        print(f"[AuthState] Password reset code resent to {email}", flush=True)
        return rx.window_alert("Verification code sent! Please check your email.")

    def complete_password_reset(self):
        """
        Step 2 of password reset.
        Verify code and update password.
        """
        self.reset_error = ""
        self.reset_loading = True

        # Validate inputs
        if not self.reset_code:
            self.reset_error = "Please enter the verification code."
            self.reset_loading = False
            return

        if not self.reset_new_password:
            self.reset_error = "Please enter a new password."
            self.reset_loading = False
            return

        if len(self.reset_new_password) < 6:
            self.reset_error = "Password must be at least 6 characters."
            self.reset_loading = False
            return

        if self.reset_new_password != self.reset_confirm_password:
            self.reset_error = "Passwords do not match."
            self.reset_loading = False
            return

        email = self.reset_email.lower().strip()

        # Verify the code
        code_valid, code_error = verify_email_code(email, self.reset_code.strip())

        if not code_valid:
            self.reset_error = code_error
            self.reset_loading = False
            return

        # Code is valid - update the password
        with rx.session() as session:
            user = session.exec(
                select(User).where(User.email == email)
            ).first()

            if not user:
                self.reset_error = "User not found. Please try again."
                self.reset_loading = False
                return

            # Hash and update the password
            user.password = hash_password(self.reset_new_password)
            session.add(user)
            session.commit()

            print(f"[AuthState] Password reset successfully for user {user.username}", flush=True)

        # Reset state and redirect to login
        self.reset_step = 1
        self.reset_error = ""
        self.reset_loading = False
        self.reset_email = ""
        self.reset_code = ""
        self.reset_new_password = ""
        self.reset_confirm_password = ""

        return rx.redirect("/login")

    def go_back_to_reset_email(self):
        """Go back to step 1 (email entry) from step 2."""
        self.reset_step = 1
        self.reset_error = ""
        self.reset_code = ""
        self.reset_new_password = ""
        self.reset_confirm_password = ""

    def reset_password_reset_state(self):
        """Reset all password reset state (when navigating away)."""
        self.reset_email = ""
        self.reset_code = ""
        self.reset_new_password = ""
        self.reset_confirm_password = ""
        self.reset_step = 1
        self.reset_error = ""
        self.reset_loading = False

    # ==================== END PASSWORD RESET METHODS ====================

    def login(self):
        """Log in a user."""
        with rx.session() as session:
            user = session.exec(
                select(User).where(User.username == self.username)
            ).first()
            if user and verify_password(self.password, user.password):
                # Upgrade plain text passwords to hashed on successful login
                if needs_rehash(user.password):
                    user.password = hash_password(self.password)
                    session.add(user)
                    session.commit()
                    print(f"[AuthState] Upgraded password hash for user {user.username}", flush=True)
                self.user = user
                self.value=0
                self._n_tasks=0

                # Ensure user exists in PostgreSQL RBAC database (for existing users)
                ensure_user_exists(user_id=user.username)

                # Ensure "Shared with you" directory exists (for existing users who signed up before this feature)
                shared_dir_exists = session.exec(
                    select(ChatDirectory).where(
                        ChatDirectory.user_id == user.id,
                        ChatDirectory.name == "Shared with you"
                    )
                ).first()
                if not shared_dir_exists:
                    shared_dir = ChatDirectory(
                        user_id=user.id,
                        name="Shared with you",
                        parent_id=None,
                        order=9999
                    )
                    session.add(shared_dir)
                    session.commit()

                # Generate JWT token for API authentication
                # Uses username as user_id for RBAC permissions
                self.jwt_token = create_access_token(user_id=user.username)
                chats_dict={}
                plot_dict = {}
                table_dict = {} 
                portfolio_dict = {}
                chat_data_dict = {}
                chat_data_table_dict = {}
                #TODO maybe use just one QA possible?
                combined_dict = {}
                combined_data_dict = {}
                for chat_single in user.chats:
                    qa_list= []
                    dp_list = []
                    table_list = []
                    portfolio_list = []
                    for qa in chat_single.qas:
                       qa_list.append(QA(question=qa.question, answer=qa.answer, created_at=qa.created_at))
                    for dp in chat_single.dataplots:
                        dp_list.append(DataPlot(plot_name=dp.plot_name,
                                                column=dp.column,
                                                xaxis=dp.xaxis,
                                                color=dp.color,
                                                title=dp.title,
                                                nickname=dp.nickname,
                                                created_at=dp.created_at
                                                )
                                       )
                    for one_table in chat_single.datatables:
                        table_list.append(DataTable(table_name=one_table.table_name,
                                                    title=one_table.title,
                                                    nickname=one_table.nickname,
                                                    created_at=one_table.created_at 
                                                    )
                                          )
                    for portfolio in chat_single.portfolios:
                        portfolio_list.append(Portfolio(
                                                portfolio_name=portfolio.portfolio_name,
                                                nickname=portfolio.nickname,
                                                id=portfolio.id,
                                                created_at=portfolio.created_at
                                                )
                                             )
                    chats_dict[chat_single.chat_title] = qa_list
                    plot_dict[chat_single.chat_title] = dp_list
                    table_dict[chat_single.chat_title] = table_list
                    portfolio_dict[chat_single.chat_title] = portfolio_list                  
                    #here the true plots and tables with data are empty will be loaded in frontend only to speed up at the start
                    chat_data_dict[chat_single.chat_title] = []
                    chat_data_table_dict[chat_single.chat_title] = []
                    #at the start do not load tables and plots for all the vhats otherwise start is very slow... will load in set_plot_frontend
                    combined_dict[chat_single.chat_title] = [("message", q, q.created_at) for q in qa_list]
                    combined_data_dict[chat_single.chat_title] = [("message", q,q.created_at) for q in qa_list]
                if len(chats_dict)>0:
                    self.chats_list = chats_dict
                    self.chats_name_plots = plot_dict
                    self.chats_name_tables = table_dict
                    self.chats_name_portfolios = portfolio_dict
                    self.chats_data_plots = chat_data_dict
                    self.chats_data_tables = chat_data_table_dict
                    self.combined_name = combined_dict
                    self.combined_content = combined_data_dict
                    self.current_chat = list(chats_dict.keys())[0]
                else:
                    self.chats_list ={
                        "Buddy": [],
                        }
                    self.chats_name_plots = {
                        "Buddy": [],
                        }
                    self.chats_name_tables = {
                        "Buddy": [],
                    }
                    self.chats_name_portfolios = {
                        "Buddy": [],
                    }
                    self.current_chat = "Buddy"

                # Load chat directories for the tree view
                self.load_directories_from_db()

                # Load user's groups for sharing functionality
                self.get_user_groups_list()

                return rx.redirect("/")
            else:
                return rx.window_alert("Invalid username or password.")

    def google_login(self):
        """
        Initiate Google OAuth login flow.

        This opens a popup window to Google's OAuth consent page. After user authenticates,
        Google will redirect back to our callback URL with the authorization code.
        The popup approach hides the URL and provides a cleaner UX.
        """
        import os

        # Google OAuth configuration
        # These should be set in your .env file after creating credentials in Google Cloud Console
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")

        if not client_id:
            print("[google_login] ERROR: GOOGLE_CLIENT_ID not configured in .env", flush=True)
            return rx.window_alert("Google login is not configured. Please contact administrator.")

        # Redirect URI should match what's configured in Google Cloud Console
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")

        # Build Google OAuth URL
        google_auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"
            "response_type=code&"
            "scope=openid%20email%20profile&"
            "access_type=offline&"
            "prompt=consent"
        )

        print(f"[google_login] Opening Google OAuth popup: {google_auth_url}", flush=True)

        # Open OAuth in a centered popup window (hides URL bar in most browsers)
        popup_script = f"""
            const width = 500;
            const height = 600;
            const left = (window.screen.width - width) / 2;
            const top = (window.screen.height - height) / 2;
            const popup = window.open(
                '{google_auth_url}',
                'Google Sign In',
                `width=${{width}},height=${{height}},left=${{left}},top=${{top}},scrollbars=yes,status=no,toolbar=no,menubar=no,location=no`
            );
            if (popup) popup.focus();
        """
        return rx.call_script(popup_script)

    def process_google_callback(self):
        """
        Process Google OAuth callback - extracts code from URL and handles authentication.

        This is called on page load of the callback page.
        It reads the 'code' query parameter from the URL.
        """
        # Get the authorization code from URL query parameters
        # In Reflex, we can access query params via router
        code = self.router.page.params.get("code", "")

        if not code:
            error = self.router.page.params.get("error", "Unknown error")
            print(f"[process_google_callback] No code received. Error: {error}", flush=True)
            return popup_aware_redirect("/login", success=False, error="Google authentication failed")

        print(f"[process_google_callback] Received authorization code: {code[:20]}...", flush=True)

        # Call the handler to complete authentication
        return self.handle_google_callback(code)

    def handle_google_callback(self, code: str):
        """
        Handle the callback from Google OAuth after user authenticates.

        This method:
        1. Exchanges the authorization code for tokens
        2. Verifies the ID token with Google
        3. Creates or logs in the user based on Google profile

        Args:
            code: Authorization code from Google OAuth callback
        """
        import os
        import requests

        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")

        if not client_id or not client_secret:
            print("[handle_google_callback] ERROR: Google OAuth credentials not configured", flush=True)
            return popup_aware_error("Google login configuration error.")

        # Exchange authorization code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }

        try:
            response = requests.post(token_url, data=token_data, timeout=10)

            if response.status_code != 200:
                print(f"[handle_google_callback] Token exchange failed: {response.text}", flush=True)
                return popup_aware_error("Failed to authenticate with Google. Please try again.")

            tokens = response.json()
            id_token = tokens.get("id_token")

            if not id_token:
                print("[handle_google_callback] No ID token in response", flush=True)
                return popup_aware_error("Failed to get user information from Google.")

            # Verify the ID token and get user info
            user_info = verify_google_token(id_token)

            if not user_info:
                print("[handle_google_callback] Token verification failed", flush=True)
                return popup_aware_error("Failed to verify Google authentication.")

            email = user_info.get("email")
            name = user_info.get("name", email.split("@")[0] if email else "User")
            google_id = user_info.get("sub")

            print(f"[handle_google_callback] SUCCESS - User: {email}, Name: {name}, Google ID: {google_id}", flush=True)

            # Now login or create the user
            return self._login_or_create_google_user(email, name, google_id)

        except requests.exceptions.RequestException as e:
            print(f"[handle_google_callback] Request error: {e}", flush=True)
            return popup_aware_error("Network error during Google authentication.")
        except Exception as e:
            print(f"[handle_google_callback] Unexpected error: {e}", flush=True)
            return popup_aware_error("An error occurred during Google authentication.")

    def _sanitize_email_for_username(self, email: str) -> str:
        """
        Sanitize email to create a safe username for file paths.

        Replaces @ and . with underscores to avoid issues when username
        is used in file paths.

        Args:
            email: User's email address

        Returns:
            Sanitized username safe for file paths
        """
        # Replace @ with _at_ and . with _ to make it filesystem-safe
        # but still readable/identifiable
        sanitized = email.replace("@", "_at_").replace(".", "_")
        return sanitized

    def _login_or_create_google_user(self, email: str, name: str, google_id: str):
        """
        Login existing user or create new user from Google OAuth.

        IMPORTANT: Checks by EMAIL first to avoid duplicate accounts.
        If user exists with this email (from normal signup or previous OAuth),
        log them into that existing account.

        Args:
            email: User's email from Google
            name: User's display name from Google
            google_id: Google's unique user ID
        """
        import secrets

        email_lower = email.lower().strip()
        # Sanitize email for safe use in file paths (only used if creating new user)
        sanitized_username = self._sanitize_email_for_username(email)

        with rx.session() as session:
            session.expire_on_commit = False

            # FIRST: Check if user already exists by EMAIL (primary check)
            user = session.exec(
                select(User).where(User.email == email_lower)
            ).first()

            # FALLBACK: Also check by sanitized username (for backwards compatibility)
            if not user:
                user = session.exec(
                    select(User).where(User.username == sanitized_username)
                ).first()
                # If found by username but email is empty, update the email
                if user and not user.email:
                    user.email = email_lower
                    session.add(user)
                    session.commit()
                    print(f"[_login_or_create_google_user] Updated email for existing user: {user.username}", flush=True)

            if user:
                # Existing user - log them in
                print(f"[_login_or_create_google_user] Existing user login: {email}", flush=True)
                self.user = user
                self.value = 0
                self._n_tasks = 0

                # Ensure user exists in PostgreSQL RBAC database
                ensure_user_exists(user_id=user.username)

                # Ensure "Shared with you" directory exists
                shared_dir_exists = session.exec(
                    select(ChatDirectory).where(
                        ChatDirectory.user_id == user.id,
                        ChatDirectory.name == "Shared with you"
                    )
                ).first()
                if not shared_dir_exists:
                    shared_dir = ChatDirectory(
                        user_id=user.id,
                        name="Shared with you",
                        parent_id=None,
                        order=9999
                    )
                    session.add(shared_dir)
                    session.commit()

                # Generate JWT token
                self.jwt_token = create_access_token(user_id=user.username)

                # Load user's chats (same as regular login)
                chats_dict = {}
                plot_dict = {}
                table_dict = {}
                portfolio_dict = {}
                chat_data_dict = {}
                chat_data_table_dict = {}
                combined_dict = {}
                combined_data_dict = {}

                for chat_single in user.chats:
                    qa_list = []
                    dp_list = []
                    table_list = []
                    portfolio_list = []
                    for qa in chat_single.qas:
                        qa_list.append(QA(question=qa.question, answer=qa.answer, created_at=qa.created_at))
                    for dp in chat_single.dataplots:
                        dp_list.append(DataPlot(plot_name=dp.plot_name,
                                                column=dp.column,
                                                xaxis=dp.xaxis,
                                                color=dp.color,
                                                title=dp.title,
                                                nickname=dp.nickname,
                                                created_at=dp.created_at))
                    for one_table in chat_single.datatables:
                        table_list.append(DataTable(table_name=one_table.table_name,
                                                    title=one_table.title,
                                                    nickname=one_table.nickname,
                                                    created_at=one_table.created_at))
                    for portfolio in chat_single.portfolios:
                        portfolio_list.append(Portfolio(
                            portfolio_name=portfolio.portfolio_name,
                            nickname=portfolio.nickname,
                            id=portfolio.id,
                            created_at=portfolio.created_at))
                    chats_dict[chat_single.chat_title] = qa_list
                    plot_dict[chat_single.chat_title] = dp_list
                    table_dict[chat_single.chat_title] = table_list
                    portfolio_dict[chat_single.chat_title] = portfolio_list
                    chat_data_dict[chat_single.chat_title] = []
                    chat_data_table_dict[chat_single.chat_title] = []
                    combined_dict[chat_single.chat_title] = [("message", q, q.created_at) for q in qa_list]
                    combined_data_dict[chat_single.chat_title] = [("message", q, q.created_at) for q in qa_list]

                if len(chats_dict) > 0:
                    self.chats_list = chats_dict
                    self.chats_name_plots = plot_dict
                    self.chats_name_tables = table_dict
                    self.chats_name_portfolios = portfolio_dict
                    self.chats_data_plots = chat_data_dict
                    self.chats_data_tables = chat_data_table_dict
                    self.combined_name = combined_dict
                    self.combined_content = combined_data_dict
                    self.current_chat = list(chats_dict.keys())[0]
                else:
                    self.chats_list = {"Buddy": []}
                    self.chats_name_plots = {"Buddy": []}
                    self.chats_name_tables = {"Buddy": []}
                    self.chats_name_portfolios = {"Buddy": []}
                    self.current_chat = "Buddy"

                self.load_directories_from_db()
                self.get_user_groups_list()

                return popup_aware_redirect("/", success=True)

            else:
                # New user - create account with email
                print(f"[_login_or_create_google_user] Creating new user: {email} (sanitized: {sanitized_username})", flush=True)

                # Generate a random password (user won't need it for Google login)
                random_password = secrets.token_urlsafe(32)

                # Create user with email for future duplicate prevention
                new_user = User(username=sanitized_username, email=email_lower, password=random_password)
                self.user = new_user
                session.add(new_user)
                session.commit()
                session.refresh(self.user)

                # Create default chat
                default_chat = Chats(chat_title="Buddy", user_id=self.user.id)
                session.add(default_chat)

                # Add to indexing system
                created = add_user(self.user.username)

                # Create user in PostgreSQL RBAC database
                ensure_user_exists(user_id=self.user.username)

                # Create "Shared with you" directory
                shared_dir = ChatDirectory(
                    user_id=self.user.id,
                    name="Shared with you",
                    parent_id=None,
                    order=9999
                )
                session.add(shared_dir)
                session.commit()

                # Generate JWT token
                self.jwt_token = create_access_token(user_id=self.user.username)

                # Initialize empty chat structures
                self.current_chat = "Buddy"
                self.chats_list = {"Buddy": []}
                self.chats_name_plots = {"Buddy": []}
                self.chats_name_tables = {"Buddy": []}
                self.chats_name_portfolios = {"Buddy": []}
                self.chats_data_plots = {"Buddy": []}
                self.chats_data_tables = {"Buddy": []}

                self.load_directories_from_db()
                self.get_user_groups_list()

                return popup_aware_redirect("/", success=True)

    def microsoft_login(self):
        """
        Initiate Microsoft OAuth login flow.

        This opens a popup window to Microsoft's OAuth consent page. After user authenticates,
        Microsoft will redirect back to our callback URL with the authorization code.
        The popup approach hides the URL and provides a cleaner UX.
        """
        import os
        import urllib.parse

        # Microsoft OAuth configuration
        client_id = os.getenv("MICROSOFT_CLIENT_ID", "")

        if not client_id:
            print("[microsoft_login] ERROR: MICROSOFT_CLIENT_ID not configured in .env", flush=True)
            return rx.window_alert("Microsoft login is not configured. Please contact administrator.")

        redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:3000/auth/microsoft/callback")

        # Build Microsoft OAuth URL
        # Using common endpoint to support both personal and organizational accounts
        auth_endpoint = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "response_mode": "query"
        }

        microsoft_auth_url = f"{auth_endpoint}?{urllib.parse.urlencode(params)}"

        print(f"[microsoft_login] Opening Microsoft OAuth popup: {microsoft_auth_url}", flush=True)

        # Open OAuth in a centered popup window (hides URL bar in most browsers)
        popup_script = f"""
            const width = 500;
            const height = 600;
            const left = (window.screen.width - width) / 2;
            const top = (window.screen.height - height) / 2;
            const popup = window.open(
                '{microsoft_auth_url}',
                'Microsoft Sign In',
                `width=${{width}},height=${{height}},left=${{left}},top=${{top}},scrollbars=yes,status=no,toolbar=no,menubar=no,location=no`
            );
            if (popup) popup.focus();
        """
        return rx.call_script(popup_script)

    def process_microsoft_callback(self):
        """
        Process Microsoft OAuth callback - extracts code from URL and handles authentication.

        This is called on page load of the callback page.
        It reads the 'code' query parameter from the URL.
        """
        # Get the authorization code from URL query parameters
        code = self.router.page.params.get("code", "")

        if not code:
            error = self.router.page.params.get("error", "Unknown error")
            error_description = self.router.page.params.get("error_description", "")
            print(f"[process_microsoft_callback] No code received. Error: {error}, Description: {error_description}", flush=True)
            return popup_aware_redirect("/login", success=False, error="Microsoft authentication failed")

        print(f"[process_microsoft_callback] Received authorization code: {code[:20]}...", flush=True)

        # Call the handler to complete authentication
        return self.handle_microsoft_callback(code)

    def handle_microsoft_callback(self, code: str):
        """
        Handle the callback from Microsoft OAuth after user authenticates.

        This method:
        1. Exchanges the authorization code for tokens
        2. Decodes the ID token to get user info
        3. Creates or logs in the user based on Microsoft profile

        Args:
            code: Authorization code from Microsoft OAuth callback
        """
        import os
        import requests
        import base64
        import json

        client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
        redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:3000/auth/microsoft/callback")

        if not client_id or not client_secret:
            print("[handle_microsoft_callback] ERROR: Microsoft OAuth credentials not configured", flush=True)
            return popup_aware_error("Microsoft login configuration error.")

        # Exchange authorization code for tokens
        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        token_data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }

        try:
            response = requests.post(token_url, data=token_data, timeout=10)

            if response.status_code != 200:
                print(f"[handle_microsoft_callback] Token exchange failed: {response.text}", flush=True)
                return popup_aware_error("Failed to authenticate with Microsoft. Please try again.")

            tokens = response.json()
            id_token = tokens.get("id_token")

            if not id_token:
                print("[handle_microsoft_callback] No ID token in response", flush=True)
                return popup_aware_error("Failed to get user information from Microsoft.")

            # Decode the ID token payload (JWT format: header.payload.signature)
            # We're just decoding, not verifying (verification would need MS public keys)
            parts = id_token.split(".")
            if len(parts) != 3:
                print("[handle_microsoft_callback] Invalid ID token format", flush=True)
                return popup_aware_error("Invalid response from Microsoft.")

            # Decode the payload (base64url)
            payload = parts[1]
            # Add padding if needed
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding

            user_info = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))

            email = user_info.get("email") or user_info.get("preferred_username")
            name = user_info.get("name", email.split("@")[0] if email else "User")
            microsoft_id = user_info.get("sub") or user_info.get("oid")

            if not email:
                print("[handle_microsoft_callback] No email in user info", flush=True)
                return popup_aware_error("Could not retrieve email from Microsoft account.")

            print(f"[handle_microsoft_callback] SUCCESS - User: {email}, Name: {name}, Microsoft ID: {microsoft_id}", flush=True)

            # Now login or create the user (reuse the same method as Google)
            return self._login_or_create_oauth_user(email, name, microsoft_id, "microsoft")

        except requests.exceptions.RequestException as e:
            print(f"[handle_microsoft_callback] Request error: {e}", flush=True)
            return popup_aware_error("Network error during Microsoft authentication.")
        except Exception as e:
            print(f"[handle_microsoft_callback] Unexpected error: {e}", flush=True)
            return popup_aware_error("An error occurred during Microsoft authentication.")

    def _login_or_create_oauth_user(self, email: str, name: str, oauth_id: str, provider: str):
        """
        Login existing user or create new user from OAuth (Google, Microsoft, etc).

        IMPORTANT: Checks by EMAIL first to avoid duplicate accounts.
        If user exists with this email (from normal signup or previous OAuth),
        log them into that existing account.

        Args:
            email: User's email from OAuth provider
            name: User's display name from OAuth provider
            oauth_id: OAuth provider's unique user ID
            provider: OAuth provider name (e.g., "google", "microsoft")
        """
        import secrets

        email_lower = email.lower().strip()
        # Sanitize email for safe use in file paths (only used if creating new user)
        sanitized_username = self._sanitize_email_for_username(email)

        with rx.session() as session:
            session.expire_on_commit = False

            # FIRST: Check if user already exists by EMAIL (primary check)
            user = session.exec(
                select(User).where(User.email == email_lower)
            ).first()

            # FALLBACK: Also check by sanitized username (for backwards compatibility)
            if not user:
                user = session.exec(
                    select(User).where(User.username == sanitized_username)
                ).first()
                # If found by username but email is empty, update the email
                if user and not user.email:
                    user.email = email_lower
                    session.add(user)
                    session.commit()
                    print(f"[_login_or_create_oauth_user] Updated email for existing user: {user.username}", flush=True)

            if user:
                # Existing user - log them in
                print(f"[_login_or_create_oauth_user] Existing user login via {provider}: {email}", flush=True)
                self.user = user
                self.value = 0
                self._n_tasks = 0

                # Ensure user exists in PostgreSQL RBAC database
                ensure_user_exists(user_id=user.username)

                # Ensure "Shared with you" directory exists
                shared_dir_exists = session.exec(
                    select(ChatDirectory).where(
                        ChatDirectory.user_id == user.id,
                        ChatDirectory.name == "Shared with you"
                    )
                ).first()
                if not shared_dir_exists:
                    shared_dir = ChatDirectory(
                        user_id=user.id,
                        name="Shared with you",
                        parent_id=None,
                        order=9999
                    )
                    session.add(shared_dir)
                    session.commit()

                # Generate JWT token
                self.jwt_token = create_access_token(user_id=user.username)

                # Load user's chats (same as regular login)
                chats_dict = {}
                plot_dict = {}
                table_dict = {}
                portfolio_dict = {}
                chat_data_dict = {}
                chat_data_table_dict = {}
                combined_dict = {}
                combined_data_dict = {}

                for chat_single in user.chats:
                    qa_list = []
                    dp_list = []
                    table_list = []
                    portfolio_list = []
                    for qa in chat_single.qas:
                        qa_list.append(QA(question=qa.question, answer=qa.answer, created_at=qa.created_at))
                    for dp in chat_single.dataplots:
                        dp_list.append(DataPlot(plot_name=dp.plot_name,
                                                column=dp.column,
                                                xaxis=dp.xaxis,
                                                color=dp.color,
                                                title=dp.title,
                                                nickname=dp.nickname,
                                                created_at=dp.created_at))
                    for one_table in chat_single.datatables:
                        table_list.append(DataTable(table_name=one_table.table_name,
                                                    title=one_table.title,
                                                    nickname=one_table.nickname,
                                                    created_at=one_table.created_at))
                    for portfolio in chat_single.portfolios:
                        portfolio_list.append(Portfolio(
                            portfolio_name=portfolio.portfolio_name,
                            nickname=portfolio.nickname,
                            id=portfolio.id,
                            created_at=portfolio.created_at))
                    chats_dict[chat_single.chat_title] = qa_list
                    plot_dict[chat_single.chat_title] = dp_list
                    table_dict[chat_single.chat_title] = table_list
                    portfolio_dict[chat_single.chat_title] = portfolio_list
                    chat_data_dict[chat_single.chat_title] = []
                    chat_data_table_dict[chat_single.chat_title] = []
                    combined_dict[chat_single.chat_title] = [("message", q, q.created_at) for q in qa_list]
                    combined_data_dict[chat_single.chat_title] = [("message", q, q.created_at) for q in qa_list]

                if len(chats_dict) > 0:
                    self.chats_list = chats_dict
                    self.chats_name_plots = plot_dict
                    self.chats_name_tables = table_dict
                    self.chats_name_portfolios = portfolio_dict
                    self.chats_data_plots = chat_data_dict
                    self.chats_data_tables = chat_data_table_dict
                    self.combined_name = combined_dict
                    self.combined_content = combined_data_dict
                    self.current_chat = list(chats_dict.keys())[0]
                else:
                    self.chats_list = {"Buddy": []}
                    self.chats_name_plots = {"Buddy": []}
                    self.chats_name_tables = {"Buddy": []}
                    self.chats_name_portfolios = {"Buddy": []}
                    self.current_chat = "Buddy"

                self.load_directories_from_db()
                self.get_user_groups_list()

                return popup_aware_redirect("/", success=True)

            else:
                # New user - create account with email
                print(f"[_login_or_create_oauth_user] Creating new user via {provider}: {email} (sanitized: {sanitized_username})", flush=True)

                # Generate a random password (user won't need it for OAuth login)
                random_password = secrets.token_urlsafe(32)

                # Create user with email for future duplicate prevention
                new_user = User(username=sanitized_username, email=email_lower, password=random_password)
                self.user = new_user
                session.add(new_user)
                session.commit()
                session.refresh(self.user)

                # Create default chat
                default_chat = Chats(chat_title="Buddy", user_id=self.user.id)
                session.add(default_chat)

                # Add to indexing system
                created = add_user(self.user.username)

                # Create user in PostgreSQL RBAC database
                ensure_user_exists(user_id=self.user.username)

                # Create "Shared with you" directory
                shared_dir = ChatDirectory(
                    user_id=self.user.id,
                    name="Shared with you",
                    parent_id=None,
                    order=9999
                )
                session.add(shared_dir)
                session.commit()

                # Generate JWT token
                self.jwt_token = create_access_token(user_id=self.user.username)

                # Initialize empty chat structures
                self.current_chat = "Buddy"
                self.chats_list = {"Buddy": []}
                self.chats_name_plots = {"Buddy": []}
                self.chats_name_tables = {"Buddy": []}
                self.chats_name_portfolios = {"Buddy": []}
                self.chats_data_plots = {"Buddy": []}
                self.chats_data_tables = {"Buddy": []}

                self.load_directories_from_db()
                self.get_user_groups_list()

                return popup_aware_redirect("/", success=True)
