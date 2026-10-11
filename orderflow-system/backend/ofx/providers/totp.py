"""RFC 6238 TOTP (HMAC-SHA1, 30 s, 6 digits) so no extra dependency is needed for Angel login."""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time


def totp(secret_b32: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32.replace(" ", "").upper() + "=" * (-len(secret_b32.replace(" ", "")) % 8))
    counter = int((time.time() if at is None else at) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits)
