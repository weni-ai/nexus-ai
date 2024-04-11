from django.core.management.base import BaseCommand

import uvicorn
from router.main import app


class Command(BaseCommand):
    def handle(self, *args, **options):
        uvicorn.run(app, host="0.0.0.0", port=8000)