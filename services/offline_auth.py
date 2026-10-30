import base64
import hashlib
import hmac
from datetime import datetime, timezone


def verify_offline_login(cached_auth, code, pin):
    if not isinstance(cached_auth, dict) or not isinstance(pin, str):
        return False

    cached_code = str(cached_auth.get("code") or "").strip()
    if not cached_code or cached_code.casefold() != str(code or "").strip().casefold():
        return False

    credential = cached_auth.get("credential")
    if not isinstance(credential, dict):
        return False

    try:
        iterations = int(credential["iterations"])
        if iterations != 120000:
            return False

        expires_at = datetime.fromisoformat(
            str(credential["expires_at"]).replace("Z", "+00:00")
        )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return False

        salt = base64.b64decode(credential["salt"], validate=True)
        expected = base64.b64decode(credential["verifier"], validate=True)
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, 32)
    except (KeyError, TypeError, ValueError, UnicodeError):
        return False

    return hmac.compare_digest(actual, expected)
