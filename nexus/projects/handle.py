from amqp.channel import Channel

from .consumers.project_consumer import ProjectConsumer
from .consumers.project_auth_consumer import ProjectAuthConsumer
from .consumers.flow_consumer import FlowConsumer
from .consumers.feature_version_consumer import FeatureVersionConsumer


def handle_consumers(channel: Channel) -> None:
    channel.basic_consume("nexus-ai.projects", callback=ProjectConsumer().handle)
    channel.basic_consume("recent-activity.nexus", callback=FlowConsumer().handle)
    channel.basic_consume("nexus-ai.projects.auth", callback=ProjectAuthConsumer().handle)
    channel.basic_consume("nexus-ai.feature-versions", callback=FeatureVersionConsumer().handle)
