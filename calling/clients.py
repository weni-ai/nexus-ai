import json

import httpx

# substitua conforme necessário
answerBaseUrl = "http://localhost:3000"


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
        response = await client.post(url, headers=headers, json=payload)

    text = response.text
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"raw": text}

    print("[WA←Graph] PRE_ACCEPT status=", response.status_code, "ok=", response.is_success)
    print("[WA←Graph] PRE_ACCEPT body=", body)

    return {"status": response.status_code, "ok": response.is_success, "body": body}


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
        response = await client.post(url, headers=headers, json=payload)

    text = response.text
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"raw": text}

    print("[WA←Graph] ACCEPT status=", response.status_code, "ok=", response.is_success)
    print("[WA←Graph] ACCEPT body=", body)

    return {"status": response.status_code, "ok": response.is_success, "body": body}


async def get_answer(sdp: str, call_id: str):
    url = f"{answerBaseUrl}/offers"
    headers = {"Content-Type": "application/json"}
    payload = {"sdp": sdp, "call_id": call_id}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    return data.get("sdp")
