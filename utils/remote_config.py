from typing import Any, Type, TypeAlias, TypeVar

from upstash_redis.asyncio import Redis

__all__ = ("RemoteConfig", "remote_config")

T = TypeVar("T")
JSONBasic: TypeAlias = str | int | float | bool
JSONValue: TypeAlias = JSONBasic | list["JSONValue"] | dict[str, "JSONValue"]


class RemoteConfig:
    def __init__(self):
        self.redis = Redis.from_env()

    async def _close_config(self):
        await self.redis.close()

    async def get_field(self, key: str, field: str):
        return await self.redis.hget(key, field)

    async def set_field(self, key: str, field: str, value: Any):
        await self.redis.hset(key, field, value)

    async def get_list(self, key: str):
        return await self.redis.lrange(key, 0, -1)

    async def set_list(self, key: str, value: list[Any]):
        if not value:
            await self.redis.delete(key)
        else:
            pipeline = self.redis.multi()
            pipeline.delete(key)
            pipeline.rpush(key, *value)
            await pipeline.exec()

    async def append_list(self, key: str, *values: Any):
        await self.redis.rpush(key, *values)

    async def get_dict(self, key: str):
        return await self.redis.hgetall(key)

    async def set_dict(self, key: str, value: dict[str, Any]):
        await self.redis.hmset(key, value)

    async def get_obj(self, type: Type[T], key: str) -> T | None:
        value = await self.get_dict(key)
        if not value:
            return None
        return type.from_dict(value)  # type: ignore

    async def set_obj(self, key: str, obj: Any):
        value = obj.to_dict()  # type: ignore
        await self.set_dict(key, value)

    def _join_path(self, *path: Any):
        return ".".join(["$"] + [str(p) for p in path])

    async def exists_json(self, key: str, *path: Any):
        p = self._join_path(*path)
        result = await self.redis.json.type(key, p)
        return result != []

    async def get_json(self, key: str, *path: Any):
        p = self._join_path(*path)
        value: list[JSONValue] = await self.redis.json.get(key, p)  # type: ignore
        if len(value) == 0:
            return None
        else:
            return value[0]

    async def get_json_m(self, key: str, *paths: list[Any]):
        if len(paths) == 0:
            empty: list[JSONValue | None] = []
            return empty
        if len(paths) == 1:
            # 返回结果为列表
            return [await self.get_json(key, *paths[0])]
        ps = [self._join_path(*p) for p in paths]
        value_dict: dict[str, list[JSONValue]] = await self.redis.json.get(key, *ps)  # type: ignore
        # 在paths上迭代保证返回值和输入保持一致
        values = [value_dict[p] for p in ps]
        values = [v[0] if len(v) > 0 else None for v in values]
        return values

    async def _ensure_path_exist(self, key: str, *path: Any):
        if not await self.redis.json.type(key):
            await self.redis.json.set(key, "$", {})
        empty = {}
        for p in reversed(path[:-1]):
            empty = {str(p): empty}
        await self.redis.json.merge(key, "$", empty)  # type: ignore

    async def set_json(self, key: str, *path: Any, value: Any):
        await self._ensure_path_exist(key, *path)
        p = self._join_path(*path)
        await self.redis.json.set(key, p, value)

    async def merge_json(self, key: str, *path: Any, value: Any):
        await self._ensure_path_exist(key, *path)
        p = self._join_path(*path)
        await self.redis.json.merge(key, p, value)

    async def delete_json(self, key: str, *path: Any):
        p = self._join_path(*path)
        await self.redis.json.delete(key, p)


remote_config = RemoteConfig()
