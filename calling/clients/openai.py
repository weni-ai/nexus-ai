import asyncio
import json

import requests
from django.conf import settings


async def get_realtime_answer(offer_sdp: str, agent: dict) -> str:
    url = f"https://api.openai.com/v1/realtime/calls?model=gpt-realtime"

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Accept": "*/*",
    }

    files = {
        "sdp": (None, offer_sdp),
        "session": (None, json.dumps(agent)),
    }

    def _do_post():
        response = requests.post(url, headers=headers, files=files)
        return response.text

    return await asyncio.to_thread(_do_post)
