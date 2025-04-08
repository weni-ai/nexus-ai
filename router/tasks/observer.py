from nexus.event_domain.event_observer import EventObserver


class SummaryTracesObserver(EventObserver):
    """
        This observer is responsible to:
        - Generate a summary of the traces of the action.
        - Save the summary on the database
    """
    def perform(self, inline_traces):
        pass


class RationaleObserver(EventObserver):
    """
        This observer is responsible to:
        - Validate the rationele on the traces
        - Classify if it is a good rationale to send to the user
        - Send to the user if it is valid
    """
    def perform(self, inline_traces):
        pass


class SaveTracesObserver(EventObserver):
    """
        This observer is responsible to:
        - Save the traces on s3
    """
    def perform(self, inline_traces):
        pass
