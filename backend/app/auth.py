"""认证模块：本地单机软件的极简账号体系。

设计取向
--------
- 零第三方依赖：密码用标准库 PBKDF2-HMAC-SHA256，令牌用 HMAC 签名，
  不引入 jwt/itsdangerous 等包，PyInstaller 打包体积不膨胀。
- 无状态令牌：服务端不存 session 表，令牌自带过期时间与签名，
  服务器重启不清登录态；换机拷贝 release 目录时令牌依旧有效
  （签名密钥存在 data/ 下，随目录一起走）。
- 令牌格式：`{user_id}.{过期时间戳}.{HMAC签名}`，30 天有效。

为什么不用 JWT 库：JWT 的 header.payload.signature 三段 base64
对这个场景毫无增益，明文 `uid.exp.sig` 反而便于排查。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path

from . import apppaths

TOKEN_TTL_SECONDS = 30 * 24 * 3600  # 30 天
PBKDF2_ITERATIONS = 200_000

_secret_cache: bytes | None = None


def secret_file() -> Path:
    """签名密钥的存放位置：data/token.key，随 release 目录一起拷贝。"""
    return apppaths.app_base_dir() / "data" / "token.key"


def _load_secret() -> bytes:
    """首次调用生成 256 位随机密钥并落盘，之后一直复用。

    注意：删除该文件会让所有已发令牌失效（等同于全员强制重新登录），
    这正是换密钥最简单的手段。
    """
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache

    path = secret_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        _secret_cache = path.read_bytes()
    else:
        _secret_cache = secrets.token_bytes(32)
        path.write_bytes(_secret_cache)
    return _secret_cache


# ==================== 密码 ====================


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """返回 (salt, hash)。salt 为 16 字节随机数的 hex。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), PBKDF2_ITERATIONS
    ).hex()
    return salt, digest


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), PBKDF2_ITERATIONS
    ).hex()
    # compare_digest 防时序侧信道，即使永不联网也应保持习惯
    return hmac.compare_digest(digest, expected_hash)


# ==================== 令牌 ====================


def make_token(user_id: int) -> str:
    exp = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}.{exp}"
    sig = hmac.new(_load_secret(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def parse_token(token: str) -> int | None:
    """校验签名与有效期，通过返回 user_id，否则 None。"""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    uid_raw, exp_raw, sig = parts
    if not (uid_raw.isdigit() and exp_raw.isdigit()):
        return None
    payload = f"{uid_raw}.{exp_raw}"
    expected = hmac.new(_load_secret(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    if int(exp_raw) < time.time():
        return None
    return int(uid_raw)
