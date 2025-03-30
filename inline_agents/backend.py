from abc import ABC, abstractmethod

from .team import Team


class InlineAgentsBackend(ABC):

    @abstractmethod
    def invoke_agents(self, team: Team): # TODO: Add supervisor
        pass
