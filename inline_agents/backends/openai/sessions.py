import redis, json
from agents.memory import Session


class RedisSession(Session):
    def __init__(self, session_id: str, r: redis.Redis):
        print(f"[DEBUG] RedisSession: {session_id}")
        self.key = session_id
        self.r = r

    async def get_items(self, limit=None):
        raw = self.r.lrange(self.key, 0, -(limit or 0) or -1)
        items = [json.loads(x) for x in raw]
        return items

    async def add_items(self, items):
        pipe = self.r.pipeline()
        for item in items:
            pipe.rpush(self.key, json.dumps(item))
        pipe.execute()

    async def pop_item(self):
        raw = self.r.rpop(self.key)
        return json.loads(raw) if raw else None

    async def clear_session(self):
        self.r.delete(self.key)