from typing import Type, TypeVar

from upstash_redis.asyncio import Redis

__all__ = ("RemoteConfig", "remote_config")

T = TypeVar("T")


class RemoteConfig:
    def __init__(self):
        self.redis = Redis.from_env()

    async def _close_config(self):
        await self.redis.close()

    async def get_field(self, key, field):
        return await self.redis.hget(key, field)

    async def set_field(self, key, field, value):
        return await self.redis.hset(key, field, value)

    async def get_dict(self, key):
        return await self.redis.hgetall(key)

    async def set_dict(self, key, value):
        return await self.redis.hmset(key, value)

    async def get_obj(self, type: Type[T], key) -> T:
        value = await self.get_dict(key)
        if not value:
            return None
        return type.from_dict(value)

    async def set_obj(self, key, obj: T):
        value = obj.to_dict()
        return await self.set_dict(key, value)


remote_config = RemoteConfig()
