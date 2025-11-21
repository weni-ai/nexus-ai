from dataclasses import dataclass

from nexus.event_driven.publisher.rabbitmq_publisher import RabbitMQPublisher


@dataclass
class ResolutionDTO:
    resolution: int
    project_uuid: str
    contact_urn: str
    external_id: int

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


def resolution_message(resolution_dto: ResolutionDTO):  # pragma: no cover
    publisher = RabbitMQPublisher()

    message = resolution_dto.dict()

    publisher.send_message(body=message, exchange="resolution.topic", routing_key="")
