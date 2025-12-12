import time

import amqp

from nexus.event_driven.connection.rabbitmq_connection import RabbitMQConnection


class PyAMQPConnectionBackend:
    _start_message = "[+] Connection established. Waiting for events"

    def __init__(self, handle_consumers: callable):
        self._handle_consumers = handle_consumers
        self.rabbitmq_instance = RabbitMQConnection()

    def _drain_events(self, connection: amqp.connection.Connection):
        while True:
            connection.drain_events()

    def start_consuming(self):
        while True:
            try:
                channel = self.rabbitmq_instance.channel

                self._handle_consumers(channel)

                import logging

                logging.getLogger(__name__).info(self._start_message)

                self._drain_events(self.rabbitmq_instance.connection)

            except (amqp.exceptions.AMQPError, ConnectionRefusedError, OSError) as error:
                import logging

                logger = logging.getLogger(__name__)
                logger.error("Connection error: %s", error)
                logger.info("Reconnecting in 5 seconds...")
                time.sleep(5)
                self.rabbitmq_instance._establish_connection()
            except Exception as error:
                # TODO: Handle exceptions with RabbitMQ
                import logging

                logging.getLogger(__name__).error("error on drain_events: %s %s", type(error), error)
                time.sleep(5)
                self.rabbitmq_instance._establish_connection()
