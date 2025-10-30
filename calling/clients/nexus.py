

import httpx
from django.conf import settings


async def get_manager(data: dict):
    params = {"token": settings.GATEWAY_VERIFICATION_TOKEN}
    async with httpx.AsyncClient() as client:
        response = await client.get(settings.GATEWAY_URL + "/manager", params=params)
        
    return response.json()


async def get_team():
    pass


async def get_context():
    pass
