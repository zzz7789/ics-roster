"""密码哈希与签名会话（不引入额外依赖）。

- 密码：PBKDF2-HMAC-SHA256，16 字节盐，26 万轮
- 会话：`<uid>:<exp>:<hmac_sha256>` 放进 HttpOnly Cookie，无需服务端存储
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from ..config import SECRET_FILE, SESSION_MAX_AGE

PBKDF2_ROUNDS = 260_000
_secret_cache: bytes | None = None


def get_secret() -> bytes:
    """签名密钥：优先环境变量，其次 data/secret.key，最后随机生成并落盘。"""
    global _secret_cache
    if _secret_cache:
        return _secret_cache

    env = os.getenv("ICS_ROSTER_SECRET")
    if env:
        _secret_cache = env.encode("utf-8")
        return _secret_cache

    if SECRET_FILE.exists():
        _secret_cache = SECRET_FILE.read_bytes()
        if _secret_cache:
            return _secret_cache

    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(48)
    SECRET_FILE.write_bytes(key)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except OSError:
        pass  # Windows 上不做强制
    _secret_cache = key
    return key


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def make_session(user_id: int, ttl: int | None = None) -> str:
    expires = int(time.time()) + (ttl or SESSION_MAX_AGE)
    payload = f"{user_id}:{expires}"
    signature = hmac.new(get_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def parse_session(token: str | None) -> int | None:
    """校验会话，返回 user_id；无效或过期返回 None。"""
    if not token:
        return None
    parts = token.split(":")
    if len(parts) != 3:
        return None
    uid_text, exp_text, signature = parts
    if not uid_text.isdigit() or not exp_text.isdigit():
        return None
    payload = f"{uid_text}:{exp_text}"
    expected = hmac.new(get_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    if int(exp_text) < int(time.time()):
        return None
    return int(uid_text)
