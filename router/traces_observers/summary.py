from nexus.event_domain.event_observer import EventObserver


class SummaryTracesObserver(EventObserver):
    """
        This observer is responsible to:
        - Generate a summary of the traces of the action.
        - Save the summary on the database
    """
    def perform(self, inline_traces):
        pass
