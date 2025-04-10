from nexus.event_domain.event_observer import EventObserver


class SaveTracesObserver(EventObserver):
    """
        This observer is responsible to:
        - Save the traces on s3
    """
    def perform(self, inline_traces, **kwargs):
        pass
