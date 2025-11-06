import asyncio
import json
import logging
import traceback

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay

from calling.agent import tool
from calling.clients.nexus import invoke_agents
from calling.clients.openai import get_realtime_answer
from calling.rtc_config import RTC_CONFIG
from calling.team import run_agent

from ..sessions.session import Session

logger = logging.getLogger(__name__)

from sfcommons.logs import LogRegistry

from calling.events import EventRegistry


class RTCBridge:

    relay = MediaRelay()

    @classmethod
    def _dc_send_json(cls, dc, obj):
        try:
            if getattr(dc, "readyState", None) == "open":
                dc.send(json.dumps(obj))
        except Exception as e:
            logger.error("[OAI][DC] Falha ao enviar JSON:", e)

    @classmethod
    async def _connect_openai_and_bridge(cls, session: Session, incoming_wa_track):
        wpp_connection = session.wpp_connection
        openai_connection = session.openai_connection

        if openai_connection is not None:
            try:
                send_track = cls.relay.subscribe(incoming_wa_track)
                openai_connection.addTrack(send_track)
            except Exception as e:
                logger.error("[OAI] Falha ao anexar track adicional:", e)
            return

        openai_connection = RTCPeerConnection(configuration=RTC_CONFIG)
        session.openai_connection = openai_connection
        print("[OAI] Criando PeerConnection para OpenAI")

        events_dc = None

        def _setup_events_channel(dc):
            nonlocal events_dc
            events_dc = dc

            @dc.on("open")
            async def on_open():
                await EventRegistry.notify("openai.channel.opened", session)

                tools_session = {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "tools": [tool],
                        "tool_choice": "auto",
                    },
                }

                cls._dc_send_json(dc, tools_session)
                # TODO: Send presentations
                # await asyncio.sleep(0.5)
                # cls._dc_send_json(
                #     dc,
                #     {
                #         "type": "response.create",
                #         "response": {
                #             "instructions": "Apresente-se, diga seu nome e como pode ajudar o contato. seja breve",
                #         },
                #     },
                # )

            @dc.on("message")
            async def on_message(message):
                data = json.loads(message)

                message_type = data.get("type")
                LogRegistry.log(f"OAI Message received, {message_type}", data, True)

                if message_type == "session.updated":
                    return

                if message_type == "error":
                    logger.error(f"[on_message] Error message: {data}")

                # if message_type == "conversation.item.input_audio_transcription.completed":
                #     print(time.time() - session.start)
                #     print(data)
                # if message_type == "response.function_call_arguments.done":
                #     name = data["name"]
                #     args = json.loads(data.get("arguments", {}))
                    
                #     print("Função Chamada", name, args)

                #     await EventRegistry.notify(
                #         "agent.run.started",
                #         session
                #     )

                    # input_text = args.get("relevantContextFromLastUserMessage")
                    # response = await invoke_agents(input_text)
                    
                    # response = {"output": "Oi"}

                    # await EventRegistry.notify(
                    #     "agent.run.completed",
                    #     session,
                    #     response=response,
                    # )

                    # print("Resposta:", response)

                    # cls._dc_send_json(
                    #     dc,
                    #     {
                    #         "type": "response.create",
                    #         "response": {
                    #             "instructions": response.get("output"),
                    #         },
                    #     },
                    # )

        try:
            openai_dc = openai_connection.createDataChannel("oai-events")
            session.set_openai_datachannel(openai_dc)
            _setup_events_channel(openai_dc)
        except Exception as e:

            logger.error("[OAI][DC] Falha ao criar datachannel local:", e)

        @openai_connection.on("track")
        async def on_oai_track(track):
            logger.debug("[OAI] Track recebida:", track.kind)
            if track.kind == "audio":
                try:
                    send_proxy = cls.relay.subscribe(track)
                    if getattr(session, "wpp_audio_sender", None) is not None:
                        try:
                            session.wpp_audio_sender.replaceTrack(send_proxy)
                            logger.debug("[BRIDGE] Áudio da OpenAI encaminhado para WhatsApp (replaceTrack)")
                        except Exception as e:
                            logger.error("[BRIDGE] Falha ao replaceTrack para WA:", e)
                            try:
                                wpp_connection.addTrack(send_proxy)
                                session.set_wpp_audio_track(send_proxy)
                                logger.debug("[BRIDGE] Fallback: addTrack usado")
                            except Exception as ex:
                                logger.error("[BRIDGE] Fallback addTrack falhou:", ex)
                    else:
                        try:
                            wpp_connection.addTrack(send_proxy)
                            session.set_wpp_audio_track(send_proxy)
                            logger.debug("[BRIDGE] addTrack usado (não havia sender salvo)")
                        except Exception as e:
                            logger.error("[BRIDGE] Falha ao addTrack:", e)
                except Exception as e:
                    logger.error("[BRIDGE] Falha ao encaminhar áudio da OpenAI->WA:", e)

        try:
            wa_to_oai = cls.relay.subscribe(incoming_wa_track)
            openai_connection.addTrack(wa_to_oai)
        except Exception as e:
            logger.error("[BRIDGE] Falha ao encaminhar áudio WA->OAI:", e)

        offer = await openai_connection.createOffer()
        await openai_connection.setLocalDescription(offer)

        print("[OAI] Enviando offer para OpenAI (tamanho)", len(openai_connection.localDescription.sdp or ""))

        logger.debug("[OAI] Open AI Offer:\n", openai_connection.localDescription.sdp)

        try:
            answer_sdp = await get_realtime_answer(openai_connection.localDescription.sdp)

            await openai_connection.setRemoteDescription(RTCSessionDescription(answer_sdp, "answer"))
            print("[OAI] Answer da OpenAI aplicado (tamanho)", len(answer_sdp or ""))
        except Exception as e:
            logger.error("Erro:", e)
            try:
                await openai_connection.close()
            except Exception:
                print("ERRO AO FECHAR CONEXão")
            openai_connection = None
            return

        @wpp_connection.on("connectionstatechange")
        async def wpp_on_connectionstatechange():
            print("Estado da conexão (WAP):", openai_connection.connectionState)

    @classmethod
    async def handle_offer(cls, session: Session):
        wpp_connection = session.wpp_connection

        @wpp_connection.on("track")
        def on_track(track):
            if track.kind == "audio":
                asyncio.create_task(cls._connect_openai_and_bridge(session, track))

        await wpp_connection.setRemoteDescription(RTCSessionDescription(session.offer_sdp, "offer"))

        for transceiver in wpp_connection.getTransceivers():
            if transceiver.kind == "audio":
                transceiver.direction = "sendrecv"
                session.wpp_audio_sender = transceiver.sender

        answer = await wpp_connection.createAnswer()
        await wpp_connection.setLocalDescription(answer)
        
        session.set_answer_sdp(answer.sdp)
        await EventRegistry.notify("whatspp.answer.created", session)

        return answer.sdp
