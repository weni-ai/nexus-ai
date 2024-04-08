import logging
from django.core.management.base import BaseCommand
from nexus.intelligences.models import ContentBaseFile, ContentBaseLink, ContentBaseText
from nexus.task_managers.tasks import upload_file, send_link, upload_text_file

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Command to reindex all the content bases into sentenx'

    def handle(self, *args, **options):
        # Process ContentBaseFile objects
        for cbf in ContentBaseFile.objects.filter(is_active=True):
            self.stdout.write(self.style.WARNING(f'Processing ContentBaseFile: {cbf.uuid}'))
            upload_file.delay(
                file=cbf.file,
                content_base_uuid=str(cbf.content_base.uuid),
                extension_file=cbf.extension_file,
                user_email=cbf.created_by.email,
                content_base_file_uuid=str(cbf.uuid)
            )

        self.stdout.write(self.style.SUCCESS('Finished processing ContentBaseFile objects.'))

        self.stdout.write(self.style.SUCCESS('Successfully processed all active content base objects'))
