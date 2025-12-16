import json
import os

import requests
from prometheus_client import Gauge

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver


@observer("classification_health_check")
class ZeroShotClassificationHealthCheckObserver(EventObserver):  # pragma: no cover
    def __init__(self):
        self.url = os.environ.get("HC_ZEROSHOT_URL")
        self.token = os.environ.get("HC_WENI_TOKEN")
        self.service_name = "zeroshot_classification"
        if not hasattr(ZeroShotClassificationHealthCheckObserver, "_service_health"):
            ZeroShotClassificationHealthCheckObserver._service_health = Gauge(
                "service_zeroshot_classification_health", "Health status of services", ["service_name"]
            )
        self.service_health = ZeroShotClassificationHealthCheckObserver._service_health

    def perform(self):
        if os.environ.get("ENVIRONMENT") == "production":
            actions = list(
                {
                    "class": "health check",
                    "context": "health check",
                }
            )
            payload = {"context": "health check", "language": "por", "text": "health check", "options": actions}
            headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
            try:
                response = requests.request("POST", self.url, headers=headers, data=json.dumps(payload))

                if response.status_code == 200:
                    self.service_health.labels(service_name=self.service_name).set(1)
                else:
                    self.service_health.labels(service_name=self.service_name).set(0)
            except Exception:
                self.service_health.labels(service_name=self.service_name).set(0)


@observer("health_check")
class ZeroShotHealthCheckObserver(EventObserver):  # pragma: no cover
    def __init__(self):
        self.url = os.environ.get("HC_ZEROSHOT_URL")
        self.token = os.environ.get("HC_WENI_TOKEN")
        self.service_name = "zeroshot"
        # Use class-level metric to avoid duplicate registration
        if not hasattr(ZeroShotHealthCheckObserver, "_service_health"):
            ZeroShotHealthCheckObserver._service_health = Gauge(
                "service_health_zeroshot", "Health status of services", ["service_name"]
            )
        self.service_health = ZeroShotHealthCheckObserver._service_health

    def perform(self):
        if os.environ.get("ENVIRONMENT") == "production":
            try:
                response = requests.request("GET", self.url)

                if response.status_code == 200:
                    self.service_health.labels(service_name=self.service_name).set(1)
                else:
                    self.service_health.labels(service_name=self.service_name).set(0)
            except Exception:
                self.service_health.labels(service_name=self.service_name).set(0)


@observer("health_check")
class GolfinhoHealthCheckObserver(EventObserver):  # pragma: no cover
    def __init__(self):
        self.url = os.environ.get("HC_GOLFINHO_URL")
        self.token = os.environ.get("HC_WENI_TOKEN")
        self.service_name = "wenigpt_golfinho"
        # Use class-level metric to avoid duplicate registration
        if not hasattr(GolfinhoHealthCheckObserver, "_service_health"):
            GolfinhoHealthCheckObserver._service_health = Gauge(
                "service_health_golfinho", "Health status of services", ["service_name"]
            )
        self.service_health = GolfinhoHealthCheckObserver._service_health

    def perform(self):
        if os.environ.get("ENVIRONMENT") == "production":
            try:
                response = requests.request("GET", self.url)

                if response.status_code == 200:
                    self.service_health.labels(service_name=self.service_name).set(1)
                else:
                    self.service_health.labels(service_name=self.service_name).set(0)
            except Exception:
                self.service_health.labels(service_name=self.service_name).set(0)
