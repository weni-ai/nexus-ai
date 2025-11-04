from typing import TYPE_CHECKING, Dict, List, Union

from .listener import EventListener

if TYPE_CHECKING:
    from calling.sessions import Session


class EventRegistry:
    listeners: Dict[str, List[EventListener]] = {}

    @classmethod
    def subscribe(cls, event: str, listener: Union[EventListener, List[EventListener]]):
        if event not in cls.listeners:
            cls.listeners[event] = []

        cls.listeners[event].append(listener)

    @classmethod
    async def notify(cls, event: str, session: "Session", **kwargs):
        """
        Notifies all registered listeners for a given event.

        Args:
            event (str): The name of the event to notify.
            session (Session): The current session instance providing context for the event.
            log_event (bool, optional): Whether to log the event in `LogRegistry`. Defaults to True.
            **kwargs: Additional keyword arguments to pass to each listener.

        Example:
            EventRegistry.notify(
                "agent_response",
                session=current_session,
                output="Agent's final response"
            )

        """
        listeners = cls.listeners.get(event, [])

        for listener in listeners:
            await listener.perform(event, session, **kwargs)
