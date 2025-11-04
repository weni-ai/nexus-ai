

import httpx
from django.conf import settings


async def get_agents(data: dict):
    params = {"token": settings.GATEWAY_VERIFICATION_TOKEN}
    url = settings.GATEWAY_URL + "/manager"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

    return response.json()
