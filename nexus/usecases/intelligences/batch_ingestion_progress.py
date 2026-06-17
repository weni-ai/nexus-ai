from nexus.intelligences.models import ContentBaseFile
from nexus.task_managers.models import ContentBaseFileTaskManager


class BatchIngestionProgressUseCase:
    BATCH_STATUS_PROCESSING = "processing"
    BATCH_STATUS_SUCCESS = "success"
    BATCH_STATUS_FAILED = "failed"
    BATCH_STATUS_PARTIAL = "partial"

    COMPLETED_STATUSES = {ContentBaseFileTaskManager.STATUS_SUCCESS}
    FAILED_STATUSES = {ContentBaseFileTaskManager.STATUS_FAIL}
    IN_PROGRESS_STATUSES = {
        ContentBaseFileTaskManager.STATUS_WAITING,
        ContentBaseFileTaskManager.STATUS_LOADING,
        ContentBaseFileTaskManager.STATUS_PROCESSING,
    }

    def get_progress(self, content_base_uuid: str, file_uuids: list[str]) -> dict:
        if not file_uuids:
            return self._empty_progress()

        files = list(
            ContentBaseFile.objects.filter(
                content_base__uuid=content_base_uuid,
                uuid__in=file_uuids,
            ).prefetch_related("upload_tasks")
        )

        if len(files) != len(set(file_uuids)):
            found_uuids = {str(file.uuid) for file in files}
            missing_uuids = [file_uuid for file_uuid in file_uuids if file_uuid not in found_uuids]
            raise ContentBaseFile.DoesNotExist(f"Files not found in content base: {', '.join(missing_uuids)}")

        completed = 0
        failed = 0
        remaining = 0
        failed_files = []

        files_by_uuid = {str(file.uuid): file for file in files}
        for file_uuid in file_uuids:
            content_base_file = files_by_uuid[str(file_uuid)]
            status = self._get_file_status(content_base_file)

            if status in self.COMPLETED_STATUSES:
                completed += 1
            elif status in self.FAILED_STATUSES:
                failed += 1
                failed_files.append(
                    {
                        "uuid": str(content_base_file.uuid),
                        "filename": content_base_file.file_name,
                    }
                )
            else:
                remaining += 1

        total = len(file_uuids)
        progress_percentage = self._calculate_progress_percentage(completed, total)
        is_complete = remaining == 0

        progress = {
            "total": total,
            "completed": completed,
            "failed": failed,
            "remaining": remaining,
            "progress_percentage": progress_percentage,
            "is_complete": is_complete,
            "status": self._resolve_batch_status(completed, failed, remaining),
        }

        if failed_files:
            progress["failed_files"] = failed_files

        return progress

    def _calculate_progress_percentage(self, completed: int, total: int) -> int:
        if total == 0:
            return 0
        return int((completed * 100) / total)

    def _resolve_batch_status(self, completed: int, failed: int, remaining: int) -> str:
        if remaining > 0:
            return self.BATCH_STATUS_PROCESSING
        if failed == 0:
            return self.BATCH_STATUS_SUCCESS
        if completed == 0:
            return self.BATCH_STATUS_FAILED
        return self.BATCH_STATUS_PARTIAL

    def _get_file_status(self, content_base_file: ContentBaseFile) -> str:
        task_manager = content_base_file.upload_tasks.order_by("created_at").last()
        if task_manager is None:
            return ContentBaseFileTaskManager.STATUS_FAIL
        return task_manager.status

    def _empty_progress(self) -> dict:
        return {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "remaining": 0,
            "progress_percentage": 0,
            "is_complete": True,
            "status": self.BATCH_STATUS_SUCCESS,
        }
