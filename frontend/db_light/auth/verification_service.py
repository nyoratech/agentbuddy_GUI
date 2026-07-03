"""
Shim for db_light.auth.verification_service.

The full project stores email-verification codes in Postgres. For this minimal
build we keep them in memory, which is enough for local signup: the code is also
printed to the console by finbuddy.utils.email_sender when SMTP is not
configured, so a developer can complete signup without an email server.
"""
import random
import time
from typing import Optional, Tuple

# email -> {"code": str, "expires": float}
_PENDING: dict = {}
_TTL_SECONDS = 15 * 60


def generate_verification_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def create_pending_verification(email: str) -> Tuple[bool, str, str]:
    code = generate_verification_code()
    _PENDING[email.lower()] = {"code": code, "expires": time.time() + _TTL_SECONDS}
    return True, "Verification code generated", code


def verify_code(email: str, code: str) -> Tuple[bool, str]:
    entry = _PENDING.get(email.lower())
    if not entry:
        return False, "No pending verification for this email"
    if time.time() > entry["expires"]:
        _PENDING.pop(email.lower(), None)
        return False, "Verification code expired"
    if code.strip() != entry["code"]:
        return False, "Invalid verification code"
    _PENDING.pop(email.lower(), None)
    return True, "Email verified"


def check_email_available(email: str) -> Tuple[bool, str]:
    # Uniqueness is enforced by the Reflex User table on creation; allow here.
    return True, "Email available"


def get_pending_verification(email: str) -> Optional[dict]:
    return _PENDING.get(email.lower())


def cleanup_expired_verifications() -> int:
    now = time.time()
    expired = [e for e, v in _PENDING.items() if now > v["expires"]]
    for e in expired:
        _PENDING.pop(e, None)
    return len(expired)
