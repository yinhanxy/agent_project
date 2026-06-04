import asyncio

from app.core.rate_limit import increment_with_window


class FakeRedis:
    def __init__(self, value=0, ttl=-2):
        self.value = value
        self.ttl_value = ttl
        self.expire_calls = []

    async def incr(self, key):
        self.value += 1
        return self.value

    async def ttl(self, key):
        return self.ttl_value

    async def expire(self, key, window):
        self.ttl_value = window
        self.expire_calls.append((key, window))


def test_first_increment_sets_expiry():
    redis = FakeRedis()

    current = asyncio.run(increment_with_window(redis, "rate-limit-key", 60))

    assert current == 1
    assert redis.expire_calls == [("rate-limit-key", 60)]


def test_increment_repairs_missing_expiry():
    redis = FakeRedis(value=103, ttl=-1)

    current = asyncio.run(increment_with_window(redis, "rate-limit-key", 60))

    assert current == 104
    assert redis.expire_calls == [("rate-limit-key", 60)]
