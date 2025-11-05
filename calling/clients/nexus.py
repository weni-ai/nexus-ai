

import httpx
from django.conf import settings


async def get_agents(data: dict):
    params = {"token": settings.GATEWAY_VERIFICATION_TOKEN}
    url = settings.GATEWAY_URL + "/manager"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=60.0)


async def invoke_agents(input_text: str):
    params = {"token": settings.GATEWAY_VERIFICATION_TOKEN}
    url = settings.GATEWAY_URL + "/invoke-agents"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, params=params, json={"input_text": input_text}, timeout=60.0)
    
    return response.json()
