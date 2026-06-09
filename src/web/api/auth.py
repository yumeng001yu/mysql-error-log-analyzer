"""认证接口模块"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from jose import JWTError, jwt

from src.config import Config

router = APIRouter(prefix="/api/auth", tags=["认证"])

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_HOURS = 24


# ── Pydantic 模型 ───────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"


class VerifyResponse(BaseModel):
    valid: bool
    username: Optional[str] = None


# ── 工具函数 ────────────────────────────────────────────────

def _get_jwt_secret() -> str:
    """获取或生成 JWT 密钥"""
    config = Config()
    secret = config.get("web", "auth", "jwt_secret", default="")
    if not secret:
        secret = secrets.token_urlsafe(32)
    return secret


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    if not hashed_password:
        return False
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def _hash_password(password: str) -> str:
    """生成密码哈希"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    """创建 JWT token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=_ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, _get_jwt_secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT token"""
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[_ALGORITHM])
        return payload
    except JWTError:
        return None


def is_auth_required(request: Request) -> bool:
    """判断当前请求是否需要认证

    仅当 web.allow_remote 为 True 且 web.auth.enabled 为 True 时需要认证。
    本地访问（127.0.0.1）不需要认证。
    """
    config = Config()
    allow_remote = config.get("web", "allow_remote", default=False)
    auth_enabled = config.get("web", "auth", "enabled", default=False)

    if not allow_remote or not auth_enabled:
        return False

    # 本地访问不需要认证
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return False

    return True


async def get_current_user(request: Request) -> Optional[str]:
    """FastAPI 依赖：获取当前认证用户

    如果不需要认证，返回 None。
    如果需要认证但 token 无效，抛出 401 异常。
    """
    if not is_auth_required(request):
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = auth_header[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="认证令牌无效或已过期")

    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="认证令牌无效")

    return username


# ── API 端点 ────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    """登录接口，验证用户名密码并返回 JWT token"""
    config = Config()

    # 如果不需要认证，直接返回 token
    if not is_auth_required(request):
        token = create_access_token({"sub": "local"})
        return LoginResponse(token=token)

    # 验证用户名密码
    expected_username = config.get("web", "auth", "username", default="admin")
    password_hash = config.get("web", "auth", "password_hash", default="")

    if body.username != expected_username:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not password_hash:
        # 首次使用，自动哈希密码并存储提示
        if body.password:
            password_hash = _hash_password(body.password)
        else:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not _verify_password(body.password, password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": body.username})
    return LoginResponse(token=token)


@router.get("/verify", response_model=VerifyResponse)
async def verify_token(request: Request, user: Optional[str] = Depends(get_current_user)):
    """验证 token 有效性"""
    if user is None:
        # 不需要认证模式
        return VerifyResponse(valid=True, username="local")
    return VerifyResponse(valid=True, username=user)
