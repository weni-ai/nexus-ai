from nexus.event_driven.publisher.rabbitmq_publisher import RabbitMQPublisher

UPDATE_PROJECTS_EXCHANGE = "update-projects.topic"
PROJECT_TYPE_UPDATE_ACTION = "project_type_update"


def publish_project_type_update(*, project_uuid: str, user_email: str, is_multi_agents: bool) -> None:
    publisher = RabbitMQPublisher()
    body = {
        "project_uuid": str(project_uuid),
        "action": PROJECT_TYPE_UPDATE_ACTION,
        "user_email": user_email or "",
        "is_multi_agents": is_multi_agents,
    }
    publisher.send_message(body=body, exchange=UPDATE_PROJECTS_EXCHANGE, routing_key="")
