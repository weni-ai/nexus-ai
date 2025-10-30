from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer

ICE_SERVERS = [
    RTCIceServer(urls="stun:stun.l.google.com:19302"),
]

RTC_CONFIG = RTCConfiguration(iceServers=ICE_SERVERS)  # TODO
