from django.core.management.base import BaseCommand

import uvicorn
from router.main import app


class Command(BaseCommand):
    help = 'Run the FastAPI application with an optional port argument'

    def add_arguments(self, parser):
        parser.add_argument(
            '--port',
            type=int,
            default=8000,
            help='Port to run the server on (default: 8000)'
        )

    def handle(self, *args, **options):
        port = options['port']
        self.stdout.write(self.style.SUCCESS(f'Starting server on port {port}'))
        uvicorn.run(app, host="0.0.0.0", port=port)
