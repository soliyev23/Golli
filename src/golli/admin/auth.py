"""Admin panelga kirish: parol xeshi, kirish urinishlarini cheklash, CSRF tokeni."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

# scrypt sozlamalari: parolni taxmin qilishni qimmatlashtiradi, kirishni esa sekinlashtirmaydi.
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    """ "scrypt:<tuz>:<xesh>" — .env dagi ADMIN_PASSWORD_HASH uchun.

    Ajratgich ":": docker compose .env dagi "$..." ni o'zgaruvchi deb almashtirib yuboradi.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split(":")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=_N, r=_R, p=_P)
    return hmac.compare_digest(digest.hex(), digest_hex)


class LoginThrottle:
    """Bitta IP'dan ketma-ket noto'g'ri urinishlarni cheklaydi (parolni terib topishga qarshi)."""

    def __init__(self, attempts: int = 5, window: float = 15 * 60) -> None:
        self._attempts = attempts
        self._window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        failures = self._failures[key]
        cutoff = time.monotonic() - self._window
        while failures and failures[0] < cutoff:
            failures.popleft()
        return failures

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self._attempts

    def failed(self, key: str) -> None:
        self._recent(key).append(time.monotonic())

    def succeeded(self, key: str) -> None:
        self._failures.pop(key, None)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
