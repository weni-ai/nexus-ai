from abc import ABC, abstractmethod

from .team import Team


class InlineAgentsBackend(ABC):
    @abstractmethod
    def invoke_agents(self, team: Team):  # TODO: Add supervisor
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__
