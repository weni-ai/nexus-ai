from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer
from django.conf import settings

ICE_SERVERS = [
    RTCIceServer(
        urls=settings.TURN_SERVER_URL,
        username=settings.TURN_SERVER_USERNAME,
        credential=settings.TURN_SERVER_PASSWORD,
    ),
]

RTC_CONFIG = RTCConfiguration(iceServers=ICE_SERVERS)
