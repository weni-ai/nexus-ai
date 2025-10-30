import asyncio

from django.conf import settings
from fastapi import FastAPI, Response

from calling.api_models import CallsModel
from calling.bridge.answer import get_answer
from calling.clients.meta import accept_call, pre_accept_call
from calling.sessions import SessionManager

app = FastAPI()


@app.get("/")
def healthcheck():
    return {}


@app.post("/calls")
async def calls(body: CallsModel):
    call = body.call
    call_id = call.call_id

    print(f"received {call.event}")

    if call.event == "terminate":
        await SessionManager.close_session(call_id)
        return Response()

    if SessionManager.is_session_active(call_id):
        return Response()

    sdp_answer = await get_answer(call.session.sdp, call_id)
    await pre_accept_call(sdp_answer, call_id, settings.WA_PHONE_NUMBER, settings.WA_ACCESS_TOKEN)

    await accept_call(sdp_answer, call_id, settings.WA_PHONE_NUMBER, settings.WA_ACCESS_TOKEN)

    return Response()
