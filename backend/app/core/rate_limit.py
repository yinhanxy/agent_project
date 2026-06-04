from fastapi import Request, HTTPException

from app.db.redis_config import connect_redis
from app.core.logger_handler import logger
from app.utils.auth_utils import decode_django_jwt


async def increment_with_window(redis, key: str, window: int) -> int:
    """原子递增限流计数，并确保计数键始终带过期时间。"""
    current = await redis.incr(key)
    ttl = await redis.ttl(key)
    if current == 1 or ttl < 0:
        await redis.expire(key, window)
    return current


def rate_limit(limit: int = 1, window: int = 60):
    """
    限流依赖函数
    :param limit: 时间窗口内的最大请求数
    :param window: 时间窗口大小（秒）
    :return: 依赖函数
    """
    async def dependency(request: Request):
        # 限流身份：优先按登录用户（从 Authorization 头可选解出，不强制鉴权），
        # 拿不到再回落到客户端 IP —— 避免反代后所有人共用同一 IP 桶而互相误伤
        identity = None
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            payload = decode_django_jwt(auth[7:].strip())
            if payload and payload.get("user_id"):
                identity = f"user:{payload['user_id']}"
        if identity is None:
            client_ip = request.client.host
            if not client_ip:
                client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or 'unknown'
            identity = f"ip:{client_ip}"

        # 生成限流键（按路由路径隔离，防止不同接口共享计数器）
        path = request.url.path
        key = f"rate_limit:{path}:{identity}"

        try:
            redis = await connect_redis()
            current = await increment_with_window(redis, key, window)

            if current > limit:
                raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        except HTTPException:
            raise  # 限流命中（429），正常抛出
        except Exception as e:
            # Redis 不可用时降级放行（可用性优先），避免整站 500
            logger.warning(f"[rate_limit] Redis 不可用，放行该请求: {e}")

    return dependency

class RateLimitMiddleware:
    """
    全局限流中间件
    """
    def __init__(self, app, limit: int = 100, window: int = 60):
        self.app = app
        self.limit = limit
        self.window = window

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        # 构建请求对象
        from fastapi import Request
        request = Request(scope, receive)

        # 获取客户端IP
        client_ip = request.client.host
        if not client_ip:
            client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or 'unknown'

        # 生成限流键
        key = f"rate_limit:global:{client_ip}"

        try:
            redis = await connect_redis()
            current = await increment_with_window(redis, key, self.window)
            limited = current > self.limit
        except Exception as e:
            # Redis 不可用时降级放行（可用性优先），避免整站 500
            logger.warning(f"[rate_limit] 全局限流 Redis 不可用，放行该请求: {e}")
            await self.app(scope, receive, send)
            return

        if limited:
            from starlette.responses import JSONResponse
            response = JSONResponse(
                {"detail": "请求过于频繁，请稍后再试"},
                status_code=429
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
