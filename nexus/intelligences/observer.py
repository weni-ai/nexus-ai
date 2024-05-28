from typing import List, Dict

from nexus.usecases.logs.create import create_recent_activity
from nexus.usecases.logs.logs_dto import CreateRecentActivityDTO
from nexus.event_domain.event_observer import EventObserver


# from nexus.logs.models import RecentActivities


class IntelligenceObserver(EventObserver):

    def perform(self, event):
        print("crio aqui")
        # create_recent_activity(event)
