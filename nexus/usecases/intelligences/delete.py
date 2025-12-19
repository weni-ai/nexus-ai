from typing import List

from nexus.events import event_manager, notify_async
from nexus.intelligences.models import ContentBaseFile, ContentBaseLink
from nexus.orgs import permissions
from nexus.usecases import orgs, users
from nexus.usecases.intelligences.retrieve import RetrieveContentBaseLinkUseCase

from ...event_domain.recent_activity.msg_handler import recent_activity_message
from .exceptions import IntelligencePermissionDenied
from .get_by_uuid import get_by_contentbase_uuid, get_by_contentbasetext_uuid, get_by_intelligence_uuid


class DeleteIntelligenceUseCase:
    def __init__(self, recent_activity_message=recent_activity_message) -> None:
        self.recent_activity_message = recent_activity_message

    def delete_intelligences(self, intelligence_uuid: str, user_email: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_intelligence_uuid(intelligence_uuid)

        has_permission = permissions.can_delete_intelligence_of_org(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = get_by_intelligence_uuid(intelligence_uuid)
        intelligence_name = intelligence.name
        intelligence.delete()

        self.recent_activity_message(
            org=org,
            user=user,
            entity_name=intelligence_name,
            action="DELETE",
        )
        return True


class DeleteContentBaseUseCase:
    def __init__(self, event_manager_notify=event_manager.notify):
        self.event_manager_notify = event_manager_notify

    def delete_contentbase(self, contentbase_uuid: str, user_email: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        has_permission = permissions.can_delete_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = get_by_contentbase_uuid(contentbase_uuid)

        self.event_manager_notify(event="contentbase_activity", contentbase=contentbase, action_type="D", user=user)

        contentbase.delete()
        contentbase.intelligence.decrease_content_bases_count()

        return True

    def bulk_delete_instruction_by_id(self, content_base, ids: List[int], user):
        for instruction_id in ids:
            instruction = content_base.instructions.get(id=instruction_id)
            self.event_manager_notify(
                event="contentbase_instruction_activity",
                content_base_instruction=instruction,
                action_type="D",
                user=user,
                action_details={"old": instruction.instruction, "new": ""},
            )
            instruction.delete()
        content_base.refresh_from_db()

        # Fire cache invalidation event after all deletions
        try:
            project_uuid = str(content_base.intelligence.project.uuid)
            # Fire cache invalidation for instructions (we need to pass a dummy instruction or just project_uuid)
            # Since we're invalidating the entire instructions list, we can just pass project_uuid
            notify_async(
                event="cache_invalidation:content_base_instruction",
                project_uuid=project_uuid,
            )
        except AttributeError:
            pass  # Skip if no project (org-level content base)


class DeleteContentBaseTextUseCase:
    def __init__(self, file_database) -> None:
        self.file_database = file_database

    def delete_contentbasetext(self, contentbasetext_uuid: str, user_email: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_contentbasetext_uuid(contentbasetext_uuid)
        user = users.get_by_email(user_email)

        has_permission = permissions.can_delete_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbasetext = get_by_contentbasetext_uuid(contentbasetext_uuid)
        contentbasetext.delete()
        self.delete_content_base_text_from_index(
            contentbasetext_uuid=str(contentbasetext_uuid),
            content_base_uuid=str(contentbasetext.content_base.uuid),
            content_base_file_name=contentbasetext.file_name,
        )
        return True

    def delete_inline_contentbasetext(
        self,
        contentbasetext_uuid: str,
    ):
        contentbasetext = get_by_contentbasetext_uuid(contentbasetext_uuid)
        contentbasetext.delete()
        self.delete_content_base_text_from_index(
            contentbasetext_uuid=str(contentbasetext_uuid),
            content_base_uuid=str(contentbasetext.content_base.uuid),
            content_base_file_name=contentbasetext.file_name,
        )
        return True

    def delete_content_base_text_from_index(
        self, contentbasetext_uuid: str, content_base_uuid: str, content_base_file_name: str
    ):
        self.file_database.delete(
            content_base_uuid=content_base_uuid,
            content_base_file_uuid=contentbasetext_uuid,
            filename=content_base_file_name,
        )
        return True


class DeleteContentBaseLinkUseCase:
    def __init__(self, file_database=None) -> None:
        self.file_database = file_database

    def delete_by_uuid(self, link_uuid: str, user_email: str):
        use_case = RetrieveContentBaseLinkUseCase()
        content_base_link: ContentBaseLink = use_case.get_contentbaselink(
            contentbaselink_uuid=link_uuid, user_email=user_email
        )
        if self.file_database:
            self.file_database.delete(
                content_base_uuid=str(content_base_link.content_base.uuid),
                content_base_file_uuid=str(content_base_link.uuid),
                filename=content_base_link.link,
            )
        content_base_link.delete()

    def delete_by_object(self, content_base_link: ContentBaseLink):
        if self.file_database:
            filename: str = content_base_link.name if content_base_link.name else content_base_link.link
            self.file_database().delete(
                content_base_uuid=str(content_base_link.content_base.uuid),
                content_base_file_uuid=str(content_base_link.uuid),
                filename=filename,
            )
        content_base_link.delete()


class DeleteContentBaseFileUseCase:
    def __init__(self, file_database=None) -> None:
        self.file_database = file_database

    def delete_by_object(self, content_base_file: ContentBaseFile):
        if self.file_database:
            self.file_database().delete(
                content_base_uuid=str(content_base_file.content_base.uuid),
                content_base_file_uuid=str(content_base_file.uuid),
                filename=content_base_file.file_name,
            )
        content_base_file.delete()
