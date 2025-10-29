from fastapi import FastAPI, Response

from calling.api_models import CallsModel

app = FastAPI()


@app.get("/")
def healthcheck():
    return {}


@app.post("/calls")
async def calls(body: CallsModel):
    call = body.call

    if call.event == "terminate":
        print("received the terminate event")

    return Response()
