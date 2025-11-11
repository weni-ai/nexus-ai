

import httpx
import requests
from django.conf import settings


async def get_agents(data: dict):
    params = {"token": settings.GATEWAY_VERIFICATION_TOKEN}
    url = settings.GATEWAY_URL + "/manager"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=60.0)


def invoke_agents(input_text: str):
    params = {"token": settings.GATEWAY_VERIFICATION_TOKEN}
    url = settings.GATEWAY_URL + "/invoke-agents"

    response = requests.post(url, params=params, json={"input_text": input_text})

    return response.json()
