import logging
from abc import abstractmethod

import amqp
from sentry_sdk import capture_exception
from weni.eda.django.consumers import EDAConsumer
from weni.eda.django.consumers.signals import message_finished, message_started

logger = logging.getLogger(__name__)


class NexusWeniConsumer(EDAConsumer):
    """Nexus consumer base on weni-eda with Sentry, logging, and explicit ack/reject."""

    consumer_log_prefix: str | None = None

    def _log_prefix(self) -> str:
        return self.consumer_log_prefix or self.__class__.__name__

    def handle(self, message: amqp.Message):
        self._message = message
        message_started.send(sender=self)
        try:
            self.consume(message)
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error(
                "[%s] Message rejected",
                self._log_prefix(),
                exc_info=True,
            )
        finally:
            message_finished.send(sender=self)

    @abstractmethod
    def consume(self, message: amqp.Message):
        pass
