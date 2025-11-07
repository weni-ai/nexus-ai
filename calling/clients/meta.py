import httpx


async def pre_accept_call(sdp: str, call_id: str, phone_number_id: str, access_token: str):
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/calls"
    payload = {
        "messaging_product": "whatsapp",
        "call_id": call_id,
        "action": "PRE_ACCEPT",
        "session": {"sdp": sdp, "sdp_type": "ANSWER"},
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=30.0)

    return response.json()


async def accept_call(sdp: str, call_id: str, phone_number_id: str, access_token: str):
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/calls"
    payload = {
        "messaging_product": "whatsapp",
        "call_id": call_id,
        "action": "ACCEPT",
        "session": {"sdp": sdp, "sdp_type": "answer"},
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=30.0)

    return response.json()