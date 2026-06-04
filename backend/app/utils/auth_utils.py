import os
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any
import requests
from dotenv import load_dotenv
from jose import JWTError, jwt
import redis.asyncio as aioredis
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.failed_response import logger
from app.db.redis_config import connect_redis, set_redis_cache

load_dotenv()

# Django JWT配置
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

# 创建Bearer认证方案
security = HTTPBearer()

# Token 黑名单连接：Django 用其默认 RedisCache 把已吊销的 jti 写到 :1:blacklist:{jti}，
# 默认落在 Redis DB1（REDIS_CACHE_URL=.../1）。这里用独立连接精确查这个 key，
# 既修复了此前 FastAPI 连 DB3 永远查不到（黑名单形同虚设）的问题，也替掉了 O(N) 的 KEYS 全库扫描。
_BLACKLIST_REDIS_URL = os.getenv("REDIS_BLACKLIST_URL", "redis://127.0.0.1:6379/1")
_blacklist_redis = None


def request_django(
    method: str,
    url: str,
    token: str,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: int = 10,
):
    """请求本机 Django 服务，显式忽略系统 HTTP 代理。"""
    session = requests.Session()
    session.trust_env = False
    return session.request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=json_body,
        timeout=timeout,
    )


def _get_blacklist_redis():
    global _blacklist_redis
    if _blacklist_redis is None:
        _blacklist_redis = aioredis.from_url(_BLACKLIST_REDIS_URL, decode_responses=True)
    return _blacklist_redis


def decode_django_jwt(token: str) -> Optional[Dict[str, Any]]:
    """解析Django生成的JWT token
    
    Args:
        token: JWT token字符串
        
    Returns:
        解析后的payload，如果解析失败返回None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """从Django JWT中获取当前用户UUID
    
    Args:
        credentials: HTTP认证凭据
        
    Returns:
        用户的UUID
        
    Raises:
        HTTPException: 认证失败时抛出
    """
    token = credentials.credentials
    payload = decode_django_jwt(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 强制要求 jti 与 exp：缺失一律拒绝。正常 Django 签发的 token 都带这两项；
    # 拒绝无 jti 的 token，同时堵住"无 jti 直接绕过黑名单检查"的问题。
    jti = payload.get("jti")
    if not jti or not payload.get("exp"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 黑名单检查：精确查 Django 写入的 :1:blacklist:{jti}，用 EXISTS（O(1)，不再 KEYS 扫全库）
    try:
        revoked = await _get_blacklist_redis().exists(f":1:blacklist:{jti}")
    except Exception as e:
        # Redis 不可用时放行（可用性优先，与限流降级一致），记 warning
        logger.warning(f"[auth] 黑名单检查 Redis 不可用，放行: {e}", extra={"path": "auth_utils.get_current_user_id"})
        revoked = 0
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 从Django JWT中提取user_id（uuid）
    user_id: str = payload.get("user_id")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not find user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user_id


async def fetch_user_info_from_django_api(token: str, url: str) -> Optional[Dict[str, Any]]:
    """从Django API获取用户信息
    
    Args:
        token: JWT token字符串
        
    Returns:
        用户信息字典，如果获取失败返回None
    """

    try:
        response = request_django("GET", url, token)
        
        if response.status_code == 200:
            resp_json = response.json()
            # Django 返回 {"success":true,"data":{...}}，取内层 data
            user_data = resp_json.get("data", resp_json)
            logger.info(f"【debug】 从Django API获取用户信息成功", extra={"path": "auth_utils.fetch_user_info_from_django_api"})
            return user_data
        else:
            logger.error(f"【debug】 从Django API获取用户信息失败，status_code: {response.status_code}", extra={"path": "auth_utils.fetch_user_info_from_django_api"})
            return None
    except Exception as e:
        logger.error(f"【debug】 调用Django API时出错: {str(e)}", extra={"path": "auth_utils.fetch_user_info_from_django_api"})
        return None


async def get_current_user_is_admin(
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> bool:
    """判断当前用户是否为管理员"""
    try:
        user_info = await get_user_info_from_redis(user_id, credentials)
        if isinstance(user_info, dict):
            return bool(user_info.get("is_admin", False))
    except Exception as e:
        logger.error(f"[is_admin] exception: {e}", extra={"path": "auth_utils.get_current_user_is_admin"})
    return False


@dataclass(frozen=True)
class RequestIdentity:
    """请求级身份：知识库权限判定的统一输入。"""
    user_id: str
    is_admin: bool = False
    dept_id: Optional[str] = None
    is_dept_admin: bool = False


def build_identity(user_id: str, user_info: Optional[Dict[str, Any]]) -> "RequestIdentity":
    """从 user_info 提取身份；缺字段降级为「无部门 + 普通成员」。"""
    info = user_info if isinstance(user_info, dict) else {}
    dept_id = info.get("dept_id") or None  # "" / None 统一成 None
    return RequestIdentity(
        user_id=user_id,
        is_admin=bool(info.get("is_admin", False)),
        dept_id=dept_id,
        is_dept_admin=bool(info.get("is_dept_admin", False)),
    )


async def get_current_identity(
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> "RequestIdentity":
    """FastAPI 依赖：解析当前请求的部门身份。"""
    try:
        user_info = await get_user_info_from_redis(user_id, credentials)
    except Exception as e:
        logger.error(f"[identity] 取用户信息失败，降级为普通成员: {e}",
                     extra={"path": "auth_utils.get_current_identity"})
        user_info = None
    return build_identity(user_id, user_info)


async def get_user_info_from_redis(user_id: str, credentials: HTTPAuthorizationCredentials):
    """从Redis中获取用户信息
    
    Args:
        user_id: 用户ID
        credentials: HTTP认证凭据
        
    Returns:
        用户信息
    """
    redis_client = await connect_redis()
    key = f":1:user:{user_id}"
    
    try:
        # 从Redis中获取用户信息
        raw = await redis_client.get(key)
        if raw is None:
            # 降级调用django查询用户信息
            user_data = await fetch_user_info_from_django_api(credentials.credentials, os.getenv("DJANGO_API_URL") + "/user/detail/")
            if user_data:
                # 将用户信息存入Redis，设置过期时间为1小时
                await set_redis_cache(key, user_data, expire=3600)
            user_info = user_data
        else:
            # 如果从Redis中获取到数据，尝试将其解析为字典
            try:
                user_info = json.loads(raw)
            except json.JSONDecodeError:
                # 如果解析失败，删除旧数据并重新获取
                await redis_client.delete(key)
                user_data = await fetch_user_info_from_django_api(credentials.credentials, os.getenv("DJANGO_API_URL") + "/user/detail/")
                if user_data:
                    await set_redis_cache(key, user_data, expire=3600)
                user_info = user_data
    except UnicodeDecodeError:
        # 处理解码错误，删除旧数据并重新获取
        await redis_client.delete(key)
        user_data = await fetch_user_info_from_django_api(credentials.credentials, os.getenv("DJANGO_API_URL") + "/user/detail/")
        if user_data:
            await set_redis_cache(key, user_data, expire=3600)
        user_info = user_data

    # 兼容旧格式：如果缓存里存的是 Django 包装响应 {"success":..., "data":{...}}，解包取内层
    if isinstance(user_info, dict) and "data" in user_info and isinstance(user_info.get("data"), dict):
        user_info = user_info["data"]

    return user_info
