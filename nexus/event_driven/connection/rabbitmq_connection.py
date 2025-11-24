import time

import amqp
from django.conf import settings


class RabbitMQConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.connect()
        return cls._instance

    def _establish_connection(self):
        self.connection = amqp.Connection(
            host=settings.EDA_BROKER_HOST,
            virtual_host=settings.EDA_VIRTUAL_HOST,
            userid=settings.EDA_BROKER_USER,
            password=settings.EDA_BROKER_PASSWORD,
            port=settings.EDA_BROKER_PORT,
        )
        self.channel = self.connection.channel()

    def connect(self):
        try:
            if not hasattr(self, "connection"):
                self._establish_connection()
        except Exception as e:
            import logging

            logging.getLogger(__name__).error("Error while connecting to RabbitMQ: %s", str(e), exc_info=True)
            time.sleep(5)  # Wait until try to reconnect
            self._establish_connection()

    def make_connection(self):
        if self.connection.is_closing:
            self._establish_connection()
        return self.connection.is_alive
