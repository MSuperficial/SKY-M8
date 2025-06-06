from typing import Any, Type, TypeVar

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

    async def get_list(self, key):
        return await self.redis.lrange(key, 0, -1)

    async def set_list(self, key, value):
        if not value:
            await self.redis.delete(key)
        else:
            pipeline = self.redis.multi()
            pipeline.delete(key)
            pipeline.rpush(key, *value)
            await pipeline.exec()

    async def append_list(self, key, *values):
        await self.redis.rpush(key, *values)

    async def get_dict(self, key):
        return await self.redis.hgetall(key)

    async def set_dict(self, key, value):
        return await self.redis.hmset(key, value)

    async def get_obj(self, type: Type[T], key) -> T | None:
        value = await self.get_dict(key)
        if not value:
            return None
        return type.from_dict(value)  # type: ignore

    async def set_obj(self, key, obj: T):
        value = obj.to_dict()  # type: ignore
        return await self.set_dict(key, value)

    async def exists_json(self, key, *path):
        path = ".".join(["$"] + [str(p) for p in path])
        result = await self.redis.json.type(key, path)
        return result != []

    async def get_json(self, key, *path):
        path = ".".join(["$"] + [str(p) for p in path])
        value: list[dict[str, Any]] = await self.redis.json.get(key, path)  # type: ignore
        if len(value) == 0:
            return None
        else:
            return value[0]

    async def _ensure_path_exist(self, key, *path):
        if not await self.redis.json.type(key):
            await self.redis.json.set(key, "$", {})
        empty = {}
        for p in reversed(path[:-1]):
            empty = {str(p): empty}
        await self.redis.json.merge(key, "$", empty)  # type: ignore

    async def set_json(self, key, *path, value) -> bool:
        await self._ensure_path_exist(key, *path)
        path = ".".join(["$"] + [str(p) for p in path])
        result = await self.redis.json.set(key, path, value)
        return result

    async def merge_json(self, key, *path, value) -> bool:
        await self._ensure_path_exist(key, *path)
        path = ".".join(["$"] + [str(p) for p in path])
        result = await self.redis.json.merge(key, path, value)
        return result


remote_config = RemoteConfig()
