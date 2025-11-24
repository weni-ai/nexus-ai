import asyncio

from fastapi import FastAPI, Response

from calling.api_models import CallsModel
from calling.service import CallingService
from calling.sessions import SessionManager

app = FastAPI()


@app.get("/")
def healthcheck():
    return {}


@app.post("/calls")
async def calls(body: CallsModel):
    call = body.call
    call_id = call.call_id

    import logging

    logging.getLogger(__name__).info("Call received", extra={"event": call.event})

    if call.event == "terminate":
        await SessionManager.close_session(call_id)
        return Response()

    if SessionManager.is_session_active(call_id):
        return Response()

    asyncio.create_task(CallingService.dispatch(call.session.sdp, call_id))

    return Response()
