"""
Password hashing utilities using bcrypt via passlib.

Provides secure password hashing and verification for user authentication.
"""

from passlib.hash import bcrypt

# Use bcrypt directly with truncate_error=False to avoid 72-byte limit errors
# This setting tells passlib to silently truncate passwords > 72 bytes
bcrypt_hasher = bcrypt.using(truncate_error=False)


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string (includes salt)
    """
    return bcrypt_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against a hashed password.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Previously hashed password

    Returns:
        True if password matches, False otherwise
    """
    # Handle case where password might be plain text (legacy users)
    # bcrypt hashes always start with $2 (e.g., $2b$, $2a$, $2y$)
    if not hashed_password.startswith('$2'):
        # Plain text password - do direct comparison for legacy support
        # This allows existing users to still login
        return plain_password == hashed_password

    return bcrypt_hasher.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs to be upgraded.

    This returns True for:
    - Plain text passwords (legacy users)
    - Hashes using deprecated schemes
    - Hashes with outdated parameters

    Args:
        hashed_password: The stored password hash

    Returns:
        True if password should be rehashed on next login
    """
    # Plain text passwords need rehashing
    if not hashed_password.startswith('$2'):
        return True

    return bcrypt_hasher.needs_update(hashed_password)
