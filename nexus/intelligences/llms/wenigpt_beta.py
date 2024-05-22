from django.conf import settings
from nexus.intelligences.llms.wenigpt import WeniGPTClient


class WeniGPTBetaClient(WeniGPTClient):
    code = "wenigpt_beta"

    def __init__(self, model_version: str):
        self.url = settings.WENIGPT_BETA_API_URL
        self.token = settings.WENIGPT_BETA_API_TOKEN
        self.cookie = settings.WENIGPT_BETA_COOKIE
        self.api_key = settings.WENIGPT__BETA_OPENAI_TOKEN
        self.stop = settings.WENIGPT_BETA_STOP
