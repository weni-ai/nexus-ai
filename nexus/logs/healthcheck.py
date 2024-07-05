from nexus.events import event_manager


class HealthCheck:  # pragma: no cover
    def __init__(
        self,
        event_manager_notify=event_manager.notify
    ):
        self.event_manager_notify = event_manager_notify

    def check_service_health(self):
        self.event_manager_notify(
            event="health_check"
        )


class ClassificationHealthCheck:  # pragma: no cover
    def __init__(
        self,
        event_manager_notify=event_manager.notify
    ):
        self.event_manager_notify = event_manager_notify

    def check_service_health(self):
        self.event_manager_notify(
            event="classification_health_check"
        )
