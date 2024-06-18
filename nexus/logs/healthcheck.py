import requests
from prometheus_client import Gauge


services = {
    'service_1': 'http://service1/health',
    'service_2': 'http://service2/health',
}

service_health = Gauge('service_health', 'Health status of services', ['service_name'])


def check_service_health():
    services = {
        'service_1': 'http://service1/health',
        'service_2': 'http://service2/health',
    }

    for service_name, url in services.items():
        try:
            response = requests.get(url)
            if response.status_code == 200:
                service_health.labels(service_name=service_name).set(1)
            else:
                service_health.labels(service_name=service_name).set(0)
        except requests.exceptions.RequestException:
            service_health.labels(service_name=service_name).set(0)
