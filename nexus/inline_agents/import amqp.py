import amqp
from django.conf import settings
from weni.eda.django.connection_params import AMQConnectionParamsFactory, ConnectionParamsFactory
BROKER = "eda"  # "amq" = Amazon MQ, "eda" = RabbitMQ legado
EXCHANGE = "update-projects.topic"
if BROKER == "amq":
    params = AMQConnectionParamsFactory.get_params()
    queue = settings.PROJECT_UPDATE_AMQ_QUEUE_NAME
else:
    params = ConnectionParamsFactory.get_params()
    queue = "nexus-ai.update-projects"
connection = amqp.Connection(**params.value)
connection.connect()
channel = connection.channel()
try:
    channel.queue_declare(queue=queue, durable=True, exclusive=False, auto_delete=False)
    channel.queue_bind(queue=queue, exchange=EXCHANGE, routing_key="")
    print(f"ok: {queue} -> {EXCHANGE}")
finally:
    channel.close()
    connection.close()


from nexus.projects.models import Project
project = Project.objects.get(uuid="7b3fb137-dcd7-4866-83af-f55cdfcb907c")
