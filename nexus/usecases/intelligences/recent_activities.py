from nexus.task_managers.tasks import send_recent_activities


def create_recent_activity(
        user_email: str,
        entity_name: str,  # Intelligence name
        org_uuid: str,  # Org uuid
        entity: str = "AI",
        action: str = "CREATE",
) -> None:

    activity_data = [
        {
            "user_email": user_email,
            "entity": entity,
            "action": action,
            "entity_name": entity_name,
            "org_uuid": org_uuid
        }
    ]

    send_recent_activities.delay(activity_data)
