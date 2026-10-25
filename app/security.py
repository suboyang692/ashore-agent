"""密码哈希与 JWT（HS256）。

JWT 用标准库实现，避免引入额外依赖；签名算法固定 HS256，
解码时校验 alg 与签名，不接受 none / 其他算法。
"""
import base64
import hashlib
import hmac
import json
import time

import bcrypt

from app.config import JWT_SECRET, JWT_TTL


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: str, ttl: int = None) -> str:
    now = int(time.time())
    header = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"},
                              separators=(",", ":")).encode())
    payload = _b64e(json.dumps({"sub": user_id, "iat": now,
                                "exp": now + (ttl or JWT_TTL)},
                               separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    signature = _b64e(hmac.new(JWT_SECRET.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_token(token: str):
    """校验通过返回 payload，否则返回 None。"""
    try:
        header_b64, payload_b64, signature = token.split(".")
    except (AttributeError, ValueError):
        return None
    signing = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(JWT_SECRET.encode(), signing, hashlib.sha256).digest()
    try:
        given = _b64d(signature)
    except Exception:
        return None
    if not hmac.compare_digest(expected, given):
        return None
    try:
        header = json.loads(_b64d(header_b64))
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        return None
    if header.get("alg") != "HS256":
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
