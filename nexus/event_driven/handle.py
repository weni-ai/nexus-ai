from amqp.channel import Channel

from nexus.projects.handle import handle_consumers as project_handle_consumers
from nexus.orgs.handle import handle_consumers as orgs_handle_consumers
from nexus.inline_agents.handle import handle_consumers as inline_agents_handle_consumers


def handle_consumers(channel: Channel) -> None:
    project_handle_consumers(channel)
    orgs_handle_consumers(channel)
    inline_agents_handle_consumers(channel)
