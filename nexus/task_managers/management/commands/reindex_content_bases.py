from django.core.management.base import BaseCommand
from nexus.intelligences.models import ContentBaseFile, ContentBaseLink, ContentBaseText
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.task_managers.tasks import add_file


class Command(BaseCommand):
    help = 'Command to reindex all the content bases into sentenx'

    def handle(self, *args, **options):
        # Process ContentBaseFile objects
        for cbf in ContentBaseFile.objects.filter(is_active=True):
            self.stdout.write(self.style.WARNING(f'Queuing ContentBaseFile: {cbf.uuid}'))

            task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=cbf)
            add_file.apply_async(args=[str(task_manager.uuid), "file", "pdfminer"])

        self.stdout.write(self.style.SUCCESS('Finished queuing ContentBaseFile objects.'))

        # Process ContentBaseLink objects
        for cbl in ContentBaseLink.objects.filter(is_active=True):
            self.stdout.write(self.style.WARNING(f'Queuing ContentBaseLink UUID: {cbl.uuid}'))

            task_manager = CeleryTaskManagerUseCase().create_celery_link_manager(content_base_link=cbl)
            add_file.apply_async(args=[str(task_manager.uuid), "link"])

        self.stdout.write(self.style.SUCCESS('Finished queuing ContentBaseLink objects.'))

        # Process ContentBaseText objects
        for cbt in ContentBaseText.objects.filter(is_active=True):
            self.stdout.write(self.style.WARNING(f'Processing ContentBaseText UUID: {cbt.uuid}'))

            task_manager = CeleryTaskManagerUseCase().create_celery_text_file_manager(content_base_text=cbt)
            add_file.apply_async(args=[str(task_manager.uuid), "text"])

        self.stdout.write(self.style.SUCCESS('Finished processing ContentBaseText objects.'))
        self.stdout.write(self.style.SUCCESS('Successfully processed all active content base objects'))
