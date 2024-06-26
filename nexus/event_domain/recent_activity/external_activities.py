from nexus.event_driven.publisher.rabbitmq_publisher import RabbitMQPublisher

from nexus.event_domain.recent_activity.publishers_dto import RecentActivitiesDTO


def intelligence_activity_message(
    recent_activities_dto: RecentActivitiesDTO
):  # pragma: no cover
    publisher = RabbitMQPublisher()

    message = {
        "action": recent_activities_dto.action,
        "entity": recent_activities_dto.entity,
        "user": recent_activities_dto.user.email,
        "organization_uuid": str(recent_activities_dto.org.uuid),
        "entity_name": recent_activities_dto.entity_name
    }

    publisher.send_message(
        body=message,
        exchange="recent-activities.topic",
        routing_key=""
    )
