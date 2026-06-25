import os
import signal

from weni.eda.django.eda_app.management.commands.edaconsume import Command as WeniEDACommand

AMQ_PARAMS_CLASS = "weni.eda.django.AMQConnectionParamsFactory"
AMQ_CONNECTION_BACKEND = "weni.eda.backends.pyamqp_backend.PyAMQPConnectionBackend"
AMQ_CONSUMERS_HANDLE = "nexus.event_driven.handle_amq.handle_amq_consumers"


def handle_sigterm(*args):
    """Handle SIGTERM signal - exit gracefully."""
    print("[edaconsume_amq] - Received SIGTERM signal, exiting gracefully")
    os._exit(0)


class Command(WeniEDACommand):
    """
    Starts the Weni EDA consumer connected to the Amazon MQ broker over SSL
    (port 5671) using weni.eda.django.AMQConnectionParamsFactory.

    Used by the entrypoint.sh `edaconsume-amq` alias.
    """

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--group",
            dest="group",
            default="eda",
            help=(
                "Consumer group label, kept for parity with the entrypoint "
                "aliases. Currently informational only."
            ),
        )

    def handle(self, *args, **options):
        signal.signal(signal.SIGTERM, handle_sigterm)
        options["params_class"] = AMQ_PARAMS_CLASS
        options["handle"] = AMQ_CONSUMERS_HANDLE
        options["backend"] = AMQ_CONNECTION_BACKEND
        super().handle(*args, **options)
