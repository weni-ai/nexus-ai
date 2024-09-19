from typing import List

from nexus.events import event_manager
from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid
)
from nexus.usecases import (
    users,
    orgs
)
from ...event_domain.recent_activity.msg_handler import recent_activity_message
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied


class DeleteIntelligenceUseCase():

    def __init__(
        self,
        recent_activity_message=recent_activity_message
    ) -> None:
        self.recent_activity_message = recent_activity_message

    def delete_intelligences(
            self,
            intelligence_uuid: str,
            user_email: str
    ):
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


class DeleteContentBaseUseCase():

    def __init__(
        self,
        event_manager_notify=event_manager.notify
    ):
        self.event_manager_notify = event_manager_notify

    def delete_contentbase(
            self,
            contentbase_uuid: str,
            user_email: str
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        has_permission = permissions.can_delete_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = get_by_contentbase_uuid(contentbase_uuid)

        self.event_manager_notify(
            event="contentbase_activity",
            contentbase=contentbase,
            action_type="D",
            user=user
        )

        contentbase.delete()
        contentbase.intelligence.decrease_content_bases_count()

        return True

    def bulk_delete_instruction_by_id(self, content_base, ids: List[int], user):
        for instruction_id in ids:
            instruction = content_base.instructions.get(id=instruction_id)
            self.event_manager_notify(
                event="contentbase_instruction_activity",
                instruction=instruction,
                action_type="D",
                user=user,
                action_details={
                    "old": instruction.instruction,
                    "new": ""
                }
            )
            instruction.delete()
        content_base.refresh_from_db()


class DeleteContentBaseTextUseCase():

    def __init__(self, file_database) -> None:
        self.file_database = file_database

    def delete_contentbasetext(
            self,
            contentbasetext_uuid: str,
            user_email: str
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_contentbasetext_uuid(
            contentbasetext_uuid
        )
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

    def delete_content_base_text_from_index(self, contentbasetext_uuid: str, content_base_uuid: str, content_base_file_name: str):
        self.file_database.delete(
            content_base_uuid=content_base_uuid,
            content_base_file_uuid=contentbasetext_uuid,
            filename=content_base_file_name
        )
        return True
