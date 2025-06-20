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

    def _join_path(self, *path):
        return ".".join(["$"] + [str(p) for p in path])

    async def exists_json(self, key, *path):
        path = self._join_path(*path)
        result = await self.redis.json.type(key, path)
        return result != []

    async def get_json(self, key, *path):
        path = self._join_path(*path)
        value: list[dict[str, Any] | Any] = await self.redis.json.get(key, path)  # type: ignore
        if len(value) == 0:
            return None
        else:
            return value[0]

    async def get_json_m(self, key, *paths) -> list[Any | None]:
        if len(paths) == 0:
            return []
        if len(paths) == 1:
            # 返回结果为列表
            return [await self.get_json(key, *paths[0])]
        paths = [self._join_path(*p) for p in paths]
        value_dict: dict[str, list[Any]] = await self.redis.json.get(key, *paths)  # type: ignore
        # 在paths上迭代保证返回值和输入保持一致
        values = [value_dict[p] for p in paths]
        values = [v[0] if v else None for v in values]
        return values

    async def _ensure_path_exist(self, key, *path):
        if not await self.redis.json.type(key):
            await self.redis.json.set(key, "$", {})
        empty = {}
        for p in reversed(path[:-1]):
            empty = {str(p): empty}
        await self.redis.json.merge(key, "$", empty)  # type: ignore

    async def set_json(self, key, *path, value) -> bool:
        await self._ensure_path_exist(key, *path)
        path = self._join_path(*path)
        result = await self.redis.json.set(key, path, value)
        return result

    async def merge_json(self, key, *path, value) -> bool:
        await self._ensure_path_exist(key, *path)
        path = self._join_path(*path)
        result = await self.redis.json.merge(key, path, value)
        return result

    async def delete_json(self, key, *path):
        path = self._join_path(*path)
        await self.redis.json.delete(key, path)


remote_config = RemoteConfig()
