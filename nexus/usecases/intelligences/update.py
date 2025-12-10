import pendulum
from django.forms.models import model_to_dict

from nexus.events import event_manager, notify_async
from nexus.intelligences.models import ContentBase, ContentBaseText
from nexus.orgs import permissions
from nexus.projects.permissions import has_project_permission
from nexus.usecases import orgs, projects, users
from nexus.usecases.intelligences.intelligences_dto import UpdateContentBaseFileDTO, UpdateLLMDTO

from .exceptions import IntelligencePermissionDenied
from .get_by_uuid import (
    get_by_content_base_file_uuid,
    get_by_contentbase_uuid,
    get_by_intelligence_uuid,
    get_llm_by_project_uuid,
)


class UpdateIntelligenceUseCase:
    def update_intelligences(
        self,
        intelligence_uuid: str,
        user_email: str,
        name: str = None,
        description: str = None,
    ):
        user = users.get_by_email(user_email)
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_intelligence_uuid(intelligence_uuid)

        has_permission = permissions.can_edit_intelligence_of_org(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = get_by_intelligence_uuid(intelligence_uuid)

        if name:
            intelligence.name = name

        if description:
            intelligence.description = description

        intelligence.modified_at = pendulum.now()
        intelligence.modified_by = user
        intelligence.save()

        return intelligence


class UpdateContentBaseUseCase:
    def __init__(self, event_manager_notify=event_manager.notify):
        self.event_manager_notify = event_manager_notify

    def update_contentbase(
        self,
        contentbase_uuid: str,
        user_email: str,
        title: str = None,
        language: str = None,
        description: str = None,
    ) -> ContentBase:
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        has_permission = permissions.can_edit_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = get_by_contentbase_uuid(contentbase_uuid)
        old_contentbase_data = model_to_dict(contentbase)

        update_fields = []
        if title:
            contentbase.title = title
            update_fields.append("title")

        if language:
            contentbase.language = language
            update_fields.append("language")

        if description:
            contentbase.description = description
            update_fields.append("description")

        contentbase.modified_at = pendulum.now()
        update_fields.append("modified_at")

        contentbase.modified_by = user
        update_fields.append("modified_by")

        contentbase.save(update_fields=update_fields)
        new_contentbase_data = model_to_dict(contentbase)

        self.event_manager_notify(
            event="contentbase_activity",
            contentbase=contentbase,
            old_contentbase_data=old_contentbase_data,
            new_contentbase_data=new_contentbase_data,
            user=user,
            action_type="U",
        )

        # Fire cache invalidation event (async observer)
        notify_async(
            event="cache_invalidation:content_base",
            contentbase=contentbase,
        )

        return contentbase


class UpdateContentBaseTextUseCase:
    def __init__(self, event_manager_notify=event_manager.notify):
        self.event_manager_notify = event_manager_notify

    def update_contentbasetext(
        self,
        contentbasetext: ContentBaseText,
        user_email: str,
        text: str = None,
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbasetext_uuid(contentbasetext.uuid)

        has_permission = permissions.can_edit_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        old_contentbasetext_data = model_to_dict(contentbasetext)
        old_contentbasetext_data["modified_at"] = str(old_contentbasetext_data["modified_at"])
        if text is not None:
            contentbasetext.text = text
            contentbasetext.modified_at = pendulum.now()
            contentbasetext.modified_by = user
            contentbasetext.save(update_fields=["text", "modified_at", "modified_by"])
        new_contentbase_data = model_to_dict(contentbasetext)
        new_contentbase_data["modified_at"] = str(new_contentbase_data["modified_at"])

        self.event_manager_notify(
            event="contentbase_text_activity",
            content_base_text=contentbasetext,
            old_contentbasetext_data=old_contentbasetext_data,
            new_contentbase_data=new_contentbase_data,
            user=user,
            action_type="U",
        )

        return contentbasetext

    def update_inline_contentbasetext(
        self,
        contentbasetext: ContentBaseText,
        user_email: str,
        text: str = None,
    ):
        user = users.get_by_email(user_email)

        old_contentbasetext_data = model_to_dict(contentbasetext)
        old_contentbasetext_data["modified_at"] = str(old_contentbasetext_data["modified_at"])
        if text is not None:
            contentbasetext.text = text
            contentbasetext.modified_at = pendulum.now()
            contentbasetext.modified_by = user
            contentbasetext.save(update_fields=["text", "modified_at", "modified_by"])
        new_contentbase_data = model_to_dict(contentbasetext)
        new_contentbase_data["modified_at"] = str(new_contentbase_data["modified_at"])

        self.event_manager_notify(
            event="contentbase_text_activity",
            content_base_text=contentbasetext,
            old_contentbasetext_data=old_contentbasetext_data,
            new_contentbase_data=new_contentbase_data,
            user=user,
            action_type="U",
        )

        return contentbasetext


class UpdateContentBaseFileUseCase:
    def __init__(self, event_manager_notify=event_manager.notify) -> None:
        self.event_manager_notify = event_manager_notify

    def update_content_base_file(
        self, content_base_file_uuid: str, user_email: str, update_content_base_file_dto: UpdateContentBaseFileDTO
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbasefile_uuid(content_base_file_uuid)

        has_permission = permissions.can_edit_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        content_base_file = get_by_content_base_file_uuid(content_base_file_uuid)

        for attr, value in update_content_base_file_dto.dict().items():
            setattr(content_base_file, attr, value)
        content_base_file.modified_at = pendulum.now()
        content_base_file.modified_by = user
        content_base_file.save()

        self.event_manager_notify(
            event="contentbase_file_activity",
            content_base_file=content_base_file,
            action_type="C",
            user=user,
        )

        return content_base_file

    def update_inline_content_base_file(
        self, content_base_file_uuid: str, user_email: str, update_content_base_file_dto: UpdateContentBaseFileDTO
    ):
        user = users.get_by_email(user_email)

        content_base_file = get_by_content_base_file_uuid(content_base_file_uuid)

        for attr, value in update_content_base_file_dto.dict().items():
            setattr(content_base_file, attr, value)
        content_base_file.modified_at = pendulum.now()
        content_base_file.modified_by = user
        content_base_file.save()

        self.event_manager_notify(
            event="contentbase_file_activity",
            content_base_file=content_base_file,
            action_type="C",
            user=user,
        )

        return content_base_file


class UpdateLLMUseCase:
    def __init__(self, event_manager_notify=event_manager.notify) -> None:
        self.event_manager_notify = event_manager_notify

    def _save_log(self, llm, values_before_update, values_after_update, user) -> bool:
        action_details = {}
        for key, old_value in values_before_update.items():
            new_value = values_after_update.get(key)
            if old_value != new_value:
                if key == "setup":
                    old_token = old_value.get("token") if old_value else None
                    new_token = new_value.get("token") if new_value else None
                    if old_token != new_token:
                        if old_token:
                            old_value["token"] = "old_token"
                        if new_token:
                            new_value["token"] = "new_token"
                action_details[key] = {"old": old_value, "new": new_value}

        self.event_manager_notify(event="llm_update_activity", llm=llm, action_details=action_details, user=user)

    def update_llm_by_project(self, update_llm_dto: UpdateLLMDTO):
        project = projects.get_project_by_uuid(update_llm_dto.project_uuid)
        user = users.get_by_email(update_llm_dto.user_email)

        has_project_permission(user=user, project=project, method="PUT")

        llm = get_llm_by_project_uuid(project.uuid)
        values_before_update = model_to_dict(llm)

        for attr, value in update_llm_dto.dict().items():
            setattr(llm, attr, value)
        llm.save()

        values_after_update = model_to_dict(llm)

        self._save_log(
            llm=llm, values_before_update=values_before_update, values_after_update=values_after_update, user=user
        )

        return llm
