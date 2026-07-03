"""
JWT Token Utilities for Authentication

Handles JWT token creation and verification for user authentication.
Uses pyjwt library with HS256 algorithm.
"""

import jwt
import os
from datetime import datetime, timedelta
from typing import Optional

# Secret key for JWT signing (should be in environment variable in production)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production-12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generate a JWT access token for a user.

    Args:
        user_id: The user's ID to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        JWT token string

    Example:
        token = create_access_token(user_id="alice")
        # Returns: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": user_id,      # Subject (user_id)
        "exp": expire,        # Expiration time
        "iat": datetime.utcnow()  # Issued at
    }

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """
    Verify a JWT token and extract the user_id.

    Args:
        token: JWT token string

    Returns:
        user_id if token is valid, None otherwise

    Example:
        user_id = verify_token("eyJhbGc...")
        # Returns: "alice" or None
    """
    try:
        print(f"[verify_token] Decoding token with SECRET_KEY: {SECRET_KEY[:10]}...", flush=True)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"[verify_token] Payload decoded: {payload}", flush=True)
        user_id: str = payload.get("sub")

        if user_id is None:
            print(f"[verify_token] No 'sub' in payload!", flush=True)
            return None

        print(f"[verify_token] Success! user_id={user_id}", flush=True)
        return user_id

    except jwt.ExpiredSignatureError:
        # Token has expired
        print(f"[verify_token] Token expired!", flush=True)
        return None
    except jwt.exceptions.PyJWTError as e:
        # Invalid token
        print(f"[verify_token] PyJWTError: {e}", flush=True)
        return None


def decode_token_payload(token: str) -> Optional[dict]:
    """
    Decode a JWT token and return the full payload (for debugging).

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict or None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.exceptions.PyJWTError:
        return None


def verify_google_token(token: str) -> Optional[dict]:
    """
    Verify a Google OAuth2 ID token and extract user information.

    This function verifies the token with Google's servers and returns
    user information if the token is valid.

    Args:
        token: Google ID token string received from frontend OAuth flow

    Returns:
        Dictionary with user info (email, name, sub, etc.) if valid, None otherwise

    Example:
        user_info = verify_google_token("eyJhbGciOiJSUzI1NiIsInR5cCI6...")
        # Returns: {"email": "user@gmail.com", "name": "John Doe", "sub": "123456789"} or None
    """
    import requests

    try:
        # Google's tokeninfo endpoint for verifying ID tokens
        google_token_info_url = "https://oauth2.googleapis.com/tokeninfo"

        response = requests.get(
            google_token_info_url,
            params={"id_token": token},
            timeout=10
        )

        if response.status_code == 200:
            token_info = response.json()

            # Verify the token is for our application (optional: check aud claim)
            # You can add client ID verification here if needed:
            # expected_client_id = os.getenv("GOOGLE_CLIENT_ID")
            # if token_info.get("aud") != expected_client_id:
            #     print(f"[verify_google_token] Invalid audience: {token_info.get('aud')}")
            #     return None

            print(f"[verify_google_token] SUCCESS - Email: {token_info.get('email')}", flush=True)
            return {
                "email": token_info.get("email"),
                "email_verified": token_info.get("email_verified") == "true",
                "name": token_info.get("name", ""),
                "picture": token_info.get("picture", ""),
                "sub": token_info.get("sub"),  # Google user ID
                "given_name": token_info.get("given_name", ""),
                "family_name": token_info.get("family_name", ""),
            }
        else:
            print(f"[verify_google_token] FAILED - Status: {response.status_code}, Response: {response.text}", flush=True)
            return None

    except requests.exceptions.RequestException as e:
        print(f"[verify_google_token] Request error: {e}", flush=True)
        return None
    except Exception as e:
        print(f"[verify_google_token] Unexpected error: {e}", flush=True)
        return None
