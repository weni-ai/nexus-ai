from amqp.channel import Channel

from .consumers.flow_consumer import FlowConsumer
from .consumers.integrated_feature import (
    CreateIntegratedFeatureConsumer,
    DeleteIntegratedFeatureConsumer,
    IntegratedFeatureFlowConsumer,
    UpdateIntegratedFeatureConsumer,
)
from .consumers.project_auth_consumer import ProjectAuthConsumer
from .consumers.project_consumer import ProjectConsumer


def handle_consumers(channel: Channel) -> None:
    channel.basic_consume("nexus-ai.projects", callback=ProjectConsumer().handle)
    channel.basic_consume("recent-activity.nexus", callback=FlowConsumer().handle)
    channel.basic_consume("nexus-ai.projects.auth", callback=ProjectAuthConsumer().handle)
    channel.basic_consume("nexus.integrated-feature", callback=CreateIntegratedFeatureConsumer().handle)
    channel.basic_consume("nexus.updated-feature", callback=UpdateIntegratedFeatureConsumer().handle)
    channel.basic_consume("nexus.removed-feature", callback=DeleteIntegratedFeatureConsumer().handle)
    channel.basic_consume("nexus.created-flows", callback=IntegratedFeatureFlowConsumer().handle)
