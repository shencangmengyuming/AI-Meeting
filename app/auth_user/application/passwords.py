import base64
import hashlib
import hmac
import secrets

SCRYPT_PREFIX = "scrypt"
SCRYPT_N = 16_384
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_BYTES,
    )
    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    return (
        f"{SCRYPT_PREFIX}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{encode(salt)}${encode(digest)}"
    )


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    if not stored.startswith(f"{SCRYPT_PREFIX}$"):
        return hmac.compare_digest(password, stored), True
    try:
        _, n, r, p, salt_value, digest_value = stored.split("$", 5)
        salt = _decode(salt_value)
        expected = _decode(digest_value)
        actual = hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (TypeError, ValueError):
        return False, False
    return hmac.compare_digest(actual, expected), False


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
