import argparse
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")
django.setup()


import asyncio
import json
from dataclasses import dataclass

import requests
import uvicorn
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer
from aiortc.rtcdtlstransport import (
    RTCCertificate,
    RTCDtlsFingerprint,
    certificate_digest,
)
from decouple import config
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import PlainTextResponse

from calling.calling import get_calling_agents
from calling.clients import accept_call, pre_accept_call
from calling.functions import registry

WA_VERIFY_TOKEN = config("PROTOTYPE_WA_VERIFY_TOKEN")
WA_PHONE_NUMBER = config("PROTOTYPE_WA_PHONE_NUMBER")
WA_ACCESS_TOKEN = config("PROTOTYPE_WA_ACCESS_TOKEN")
WEBHOOK_UUID = config("PROTOTYPE_WEBHOOK_UUID")


def getFingerprints_sha256(self):
    return [RTCDtlsFingerprint("sha-256", certificate_digest(self._cert, "sha-256"))]


RTCCertificate.getFingerprints = getFingerprints_sha256


app = FastAPI()

relay = MediaRelay()

# OpenAI Realtime config
OPENAI_API_KEY = config("PROTOTYPE_OPENAI_API_KEY", "")
REALTIME_MODEL = config("REALTIME_MODEL", "gpt-realtime")


received_offers: list[str] = []
received_answers: list[str] = []


ICE_URLS = ["stun:stun.l.google.com:19302"]
ICE_SERVERS = [RTCIceServer(urls=u) for u in ICE_URLS]
RTC_CONFIG = RTCConfiguration(iceServers=ICE_SERVERS)

project: str = ""
contact_channel: str = ""


active_sessions = {}


@dataclass
class Session:
    call_id: str
    offer_sdp: str
    wpp_connection: RTCPeerConnection
    agents: dict
    openai_connection: RTCPeerConnection = None

    async def close(self):
        await self.wpp_connection.close()

        if self.openai_connection is not None:
            await self.openai_connection.close()


def _dc_send_json(dc, obj):
    # Envia JSON no data channel (ignora se não estiver aberto)
    try:
        if getattr(dc, "readyState", None) == "open":
            dc.send(json.dumps(obj))
    except Exception as e:
        print("[OAI][DC] Falha ao enviar JSON:", e)


async def _post_openai_realtime_sdp(offer_sdp: str, instructions: str) -> str:
    """POSTa o SDP de offer para a OpenAI e retorna o SDP de answer (texto)."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não definido")

    session_config = {
        "instructions": instructions,
        "type": "realtime",
        "model": "gpt-realtime",
        "audio": {
            "output": {
                "voice": "marin",
            },
        },
    }

    url = f"https://api.openai.com/v1/realtime/calls?model=gpt-realtime"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Accept": "*/*",
    }

    files = {
        "sdp": (None, offer_sdp),
        "session": (None, json.dumps(session_config)),
    }

    def _do_post():
        response = requests.post(url, headers=headers, files=files)
        return response.text

    return await asyncio.to_thread(_do_post)


async def connect_openai_and_bridge(session: Session, incoming_wa_track):
    wpp_connection = session.wpp_connection
    openai_connection = session.openai_connection

    if openai_connection is not None:
        try:
            send_track = relay.subscribe(incoming_wa_track)
            openai_connection.addTrack(send_track)
        except Exception as e:
            print("[OAI] Falha ao anexar track adicional:", e)
        return

    openai_connection = RTCPeerConnection(configuration=RTC_CONFIG)
    session.openai_connection = openai_connection
    print("[OAI] Criando PeerConnection para OpenAI")

    events_dc = None

    def _setup_events_channel(dc):
        nonlocal events_dc
        events_dc = dc

        @dc.on("open")
        def on_open():
            print("[OAI][DC] Canal oai-events aberto")
            # Registra tools e instruções na sessão Realtime

            tools_session = {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "tools": session.agents.get("tools"),
                    "tool_choice": "auto",
                },
            }

            _dc_send_json(dc, tools_session)

        @dc.on("message")
        def on_message(message):
            # print("[OAI][DC] Mensagem recebida:", message)
            try:
                data = json.loads(message)
                # print(data.get("type"))
                if data.get("type") == "response.function_call_arguments.done":
                    name = data["name"]
                    call_id = data["call_id"]
                    args = json.loads(data["arguments"])

                    function = registry.get(name)
                    if function is not None:
                        try:
                            response = function(**args)
                        except:
                            response = {"erro": "Cep não encontrado"}

                        # Envia a saída da função de volta para o Realtime (retoma a resposta do modelo)
                        try:
                            _dc_send_json(
                                dc,
                                {
                                    "type": "response.function_call_output",
                                    "call_id": call_id,
                                    "output": json.dumps(response, ensure_ascii=False),
                                },
                            )
                        except Exception as e:
                            print("[OAI][DC] Falha ao enviar saída da função:", e)

                        print(f"Response: {response}")

                        # Garante que o assistente fale o resultado em áudio
                        try:
                            if isinstance(response, dict):
                                result_text = response.get("resposta") or json.dumps(response, ensure_ascii=False)
                            else:
                                result_text = str(response)

                            cep_value = args.get("cep") if isinstance(args, dict) else None
                            spoken_text = (
                                f"O CEP {cep_value} corresponde a {result_text}."
                                if cep_value
                                else f"Resultado: {result_text}."
                            )

                            _dc_send_json(
                                dc,
                                {
                                    "type": "response.create",
                                    "response": {
                                        "instructions": spoken_text,
                                        # respeita as configurações de áudio já definidas na sessão
                                    },
                                },
                            )
                        except Exception as e:
                            print("[OAI][DC] Falha ao solicitar resposta de voz:", e)

                    print(f"Função chamada: {name} com {args}")
            except Exception:
                pass

    try:
        _setup_events_channel(openai_connection.createDataChannel("oai-events"))
    except Exception as e:
        print("[OAI][DC] Falha ao criar datachannel local:", e)

    @openai_connection.on("track")
    async def on_oai_track(track):
        print("[OAI] Track recebida:", track.kind)
        if track.kind == "audio":
            try:
                send_proxy = relay.subscribe(track)
                if getattr(session, "wpp_audio_sender", None) is not None:
                    try:
                        await session.wpp_audio_sender.replaceTrack(send_proxy)
                        print("[BRIDGE] Áudio da OpenAI encaminhado para WhatsApp (replaceTrack)")
                    except Exception as e:
                        print("[BRIDGE] Falha ao replaceTrack para WA:", e)
                        try:
                            wpp_connection.addTrack(send_proxy)
                            print("[BRIDGE] Fallback: addTrack usado")
                        except Exception as ex:
                            print("[BRIDGE] Fallback addTrack falhou:", ex)
                else:
                    try:
                        wpp_connection.addTrack(send_proxy)
                        print("[BRIDGE] addTrack usado (não havia sender salvo)")
                    except Exception as e:
                        print("[BRIDGE] Falha ao addTrack:", e)
                print("[BRIDGE] Áudio da OpenAI encaminhado para WhatsApp (addTrack)")
            except Exception as e:
                print("[BRIDGE] Falha ao encaminhar áudio da OpenAI->WA:", e)

    try:
        wa_to_oai = relay.subscribe(incoming_wa_track)
        openai_connection.addTrack(wa_to_oai)
    except Exception as e:
        print("[BRIDGE] Falha ao encaminhar áudio WA->OAI:", e)

    offer = await openai_connection.createOffer()
    await openai_connection.setLocalDescription(offer)
    print("[OAI] Enviando offer para OpenAI (tamanho)", len(openai_connection.localDescription.sdp or ""))

    try:
        answer_sdp = await _post_openai_realtime_sdp(
            openai_connection.localDescription.sdp, session.agents.get("instructions")
        )
        await openai_connection.setRemoteDescription(RTCSessionDescription(answer_sdp, "answer"))
        print("[OAI] Answer da OpenAI aplicado (tamanho)", len(answer_sdp or ""))
    except Exception as e:
        print("[OAI] Falha ao negociar com OpenAI:", e)
        try:
            await openai_connection.close()
        except Exception:
            pass
        openai_connection = None
        return

    @openai_connection.on("connectionstatechange")
    async def on_connectionstatechange():
        print("[DEBUG] Estado da conexão (OAI):", openai_connection.connectionState)

    @openai_connection.on("iceconnectionstatechange")
    async def on_oai_ice():
        print("[DEBUG] ICE (OAI):", openai_connection.iceConnectionState)

    @openai_connection.on("icegatheringstatechange")
    async def on_oai_ice_gather():
        print("[DEBUG] ICE gather (OAI):", openai_connection.iceGatheringState)

    @wpp_connection.on("iceconnectionstatechange")
    def on_wpp_ice():
        print("[DEBUG] ICE (WA):", wpp_connection.iceConnectionState)

    # @wpp_connection.on("icegatheringstatechange")
    # def on_wpp_ice_gather():
    #     print("[DEBUG] ICE gather (WA):", wpp_connection.iceGatheringState)

    @wpp_connection.on("connectionstatechange")
    def on_wpp_conn_state():
        print("[DEBUG] Estado da conexão (WA):", wpp_connection.connectionState)


async def handle_offer(session: Session):
    wpp_connection = session.wpp_connection

    @wpp_connection.on("track")
    def on_track(track):
        print(f"[{session.call_id}] Track recebida: {track.kind}")
        if track.kind == "audio":
            asyncio.create_task(connect_openai_and_bridge(session, track))

    await wpp_connection.setRemoteDescription(RTCSessionDescription(session.offer_sdp, "offer"))

    for transceiver in wpp_connection.getTransceivers():
        if transceiver.kind == "audio":
            transceiver.direction = "sendrecv"
            session.wpp_audio_sender = transceiver.sender

    answer = await wpp_connection.createAnswer()
    await wpp_connection.setLocalDescription(answer)

    return answer.sdp


async def get_answer(sdp: str, call_id: str):
    print("[Get Answer] Recebendo offer")

    message_dict = {
        "project_uuid": project,
        "text": "Sample",
        "contact_urn": "ext:260257732924@",
        "channel_uuid": contact_channel,
        "contact_name": "260257732924@",
    }

    agents = get_calling_agents(message_dict)

    wpp_connection = RTCPeerConnection(configuration=RTC_CONFIG)
    session = Session(call_id, sdp, wpp_connection, agents)

    active_sessions[call_id] = session
    answer_sdp = await handle_offer(session=session)

    return answer_sdp


async def end_call(call_id: str):
    print("[End call] Encerrando a call")
    try:
        session = active_sessions.pop(call_id)
        await session.close()
    except Exception:
        pass


@app.get(f"/{WEBHOOK_UUID}/webhook")
async def verify_webhook(request: Request):
    verify = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if verify == WA_VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    else:
        return Response(content="Invalid token", status_code=status.HTTP_403_FORBIDDEN)


@app.post(f"/{WEBHOOK_UUID}/webhook")
async def receive_webhook(request: Request):
    body = await request.json()

    try:
        change = body["entry"][0]["changes"][0]
    except (KeyError, IndexError):
        return Response(status_code=200)

    if change.get("field") == "calls":
        print("[WEBHOOK] Ligação recebida")

        value = change.get("value", {})
        calls = value.get("calls", [])
        call_data = calls[0] if calls else {}
        sdp = call_data.get("session", {}).get("sdp")
        call_id = call_data.get("id")

        if not sdp:
            event = call_data.get("event")
            if event == "terminate":
                await end_call(call_id)
            return Response(status_code=200)

        sdp_answer = await get_answer(sdp, call_id)
        await pre_accept_call(sdp_answer, call_id, WA_PHONE_NUMBER, WA_ACCESS_TOKEN)

        # pequeno atraso antes do ACCEPT
        await asyncio.sleep(0.8)

        await accept_call(sdp_answer, call_id, WA_PHONE_NUMBER, WA_ACCESS_TOKEN)

        return Response(status_code=200)

    return Response(status_code=200)


async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=3000, log_level="info")
    server = uvicorn.Server(config)

    await server.serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove o campo 'strict' de cada tool em um arquivo JSON/dict.")
    parser.add_argument(
        "--project",
        dest="project",
        help="Projeto onde o protótipo buscará os dados",
        default="9af5f63f-20e6-47d0-8e7b-e089aef4115c",
    )
    parser.add_argument(
        "--channel", dest="channel", help="Canal do contato", default="4c81eaea-b413-4859-8de2-4ff5dba27458"
    )

    args = parser.parse_args()

    project = args.project
    contact_channel = args.channel

    asyncio.run(main())
