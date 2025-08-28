import redis, json
from agents.memory import Session
from typing import Dict, Any, List

TURN_ROLES = {"user", "assistant"}
TURN_TYPES = {"message_input_item", "message_output_item"}
WATERMARK_TYPE = "watermark"


async def only_turns(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for item in items:
        role = item.get("role")
        turn_type = item.get("type") or item.get("item", {}).get("type")

        if role in TURN_ROLES and turn_type in TURN_TYPES:
            out.append(item)

    return out


async def get_watermark(session, ns: str) -> int:
    items = await session.get_items()

    for item in reversed(items):
        if item.get("type") == WATERMARK_TYPE and item.get("ns") == ns:
            return int(item.get("cursor", 0))

    return 0


async def set_watermark(session, ns: str, cursor: int):
    await session.add_items([{
        "type": WATERMARK_TYPE,
        "ns": ns,
        "cursor": int(cursor)
    }])



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


def make_session_factory(redis: redis.Redis, base_id: str):
    def for_agent(agent_name: str | None = None):
        key = f"{base_id}:{agent_name}"
        return RedisSession(key, redis)
    return for_agent
