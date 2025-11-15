import asyncio

from fastapi import FastAPI, Response, Request, HTTPException

from calling.api_models import CallsModel
from calling.service import CallingService
from calling.sessions import SessionManager

from django.conf import settings

app = FastAPI()


@app.get("/")
def healthcheck():
    return {}


def _validate_request_authorization(request: Request) -> bool:
    authorization = request.headers.get("authorization")

    if authorization is None:
        return False

    return authorization == settings.CALLING_API_AUTHORIZATION


@app.post("/calls")
async def calls(body: CallsModel, request: Request):
    if not _validate_request_authorization(request):
        raise HTTPException(status_code=401, detail="Invalid authorization")

    call = body.call
    call_id = call.call_id

    contact_urn = f"whatsapp:{body.call.to}" # TODO: Ajustar courier pra enviar

    if call.event == "terminate":
        await SessionManager.close_session(call_id)
        return Response()

    if SessionManager.is_session_active(call_id):
        return Response()

    asyncio.create_task(CallingService.dispatch(body))

    return Response()
