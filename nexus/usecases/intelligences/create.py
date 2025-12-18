import pendulum
from django.conf import settings
from django.core.exceptions import ValidationError

from nexus.events import event_manager, notify_async
from nexus.intelligences.models import (
    LLM,
    ContentBase,
    ContentBaseAgent,
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseText,
    Conversation,
    IntegratedIntelligence,
    Intelligence,
)
from nexus.orgs import permissions
from nexus.projects.models import Project
from nexus.usecases import (
    intelligences,
    orgs,
    projects,
    users,
)
from nexus.usecases.intelligences.intelligences_dto import (
    LLMDTO,
    ContentBaseDTO,
    ContentBaseFileDTO,
    ContentBaseLinkDTO,
    ContentBaseTextDTO,
)
from nexus.users.models import User

from .exceptions import IntelligencePermissionDenied


class CreateIntelligencesUseCase:
    def __init__(self, event_manager_notify=event_manager.notify) -> None:
        self.event_manager_notify = event_manager_notify

    def create_intelligences(
        self, org_uuid: str, user_email: str, name: str, description: str = None, is_router: bool = False
    ):
        org = orgs.get_by_uuid(org_uuid)
        user = users.get_by_email(user_email)

        has_permission = permissions.can_create_intelligence_in_org(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = Intelligence.objects.create(
            name=name, description=description, org=org, created_by=user, is_router=is_router
        )
        self.event_manager_notify(event="intelligence_create_activity", intelligence=intelligence)
        return intelligence


class CreateContentBaseUseCase:
    def __init__(
        self,
        event_manager_notify=event_manager.notify,
    ) -> None:
        self.event_manager_notify = event_manager_notify

    def create_contentbase(
        self,
        intelligence_uuid: str,
        user_email: str,
        title: str,
        description: str = None,
        language: str = "pt-br",
        is_router: bool = False,
    ) -> ContentBase:
        org_usecase = orgs.GetOrgByIntelligenceUseCase()
        org = org_usecase.get_org_by_intelligence_uuid(intelligence_uuid)
        user = users.get_by_email(user_email)

        has_permission = permissions.can_create_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = intelligences.get_by_intelligence_uuid(intelligence_uuid)
        contentbase = ContentBase.objects.create(
            title=title,
            intelligence=intelligence,
            created_by=user,
            description=description,
            language=language,
            is_router=is_router,
        )
        ContentBaseAgent.objects.create(
            content_base=contentbase,
            personality=settings.DEFAULT_AGENT_PERSONALITY,
        )
        intelligence.increase_content_bases_count()

        self.event_manager_notify(event="contentbase_activity", contentbase=contentbase, action_type="C", user=user)

        # Fire cache invalidation event if this is a router content base (project-level)
        if is_router:
            try:
                from nexus.intelligences.models import IntegratedIntelligence

                IntegratedIntelligence.objects.get(intelligence=intelligence)  # Validates it's integrated
                notify_async(
                    event="cache_invalidation:content_base",
                    contentbase=contentbase,
                )
            except Exception:
                pass  # Skip if no project (org-level content base)

        return contentbase


class CreateContentBaseTextUseCase:
    def create_contentbasetext(
        self,
        content_base_dto: ContentBaseDTO,
        content_base_text_dto: ContentBaseTextDTO,
    ) -> ContentBaseText:
        org_usecase = orgs.GetOrgByIntelligenceUseCase()
        org = org_usecase.get_org_by_contentbase_uuid(content_base_dto.uuid)
        user = users.get_by_email(content_base_dto.created_by_email)

        has_permission = permissions.can_create_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = intelligences.get_by_contentbase_uuid(content_base_dto.uuid)
        contentbasetext = ContentBaseText.objects.create(
            text=content_base_text_dto.text,
            content_base=contentbase,
            created_by=user,
            file=content_base_text_dto.file,
            file_name=content_base_text_dto.file_name,
        )
        return contentbasetext


class CreateContentBaseFileUseCase:
    def create_content_base_file(self, content_base_file: ContentBaseFileDTO) -> ContentBaseFile:
        user = users.get_by_email(content_base_file.user_email)
        content_base = intelligences.get_by_contentbase_uuid(contentbase_uuid=content_base_file.content_base_uuid)
        content_base_file = ContentBaseFile.objects.create(
            file_name=content_base_file.file_name,
            file=content_base_file.file_url,
            extension_file=content_base_file.extension_file,
            content_base=content_base,
            created_by=user,
        )

        return content_base_file


def create_integrated_intelligence(
    intelligence_uuid: str,
    user_email: str,
    project_uuid: str,
) -> IntegratedIntelligence:
    intelligence = intelligences.get_by_intelligence_uuid(intelligence_uuid)
    org = intelligence.org
    project_usecase = projects.ProjectsUseCase()
    project = project_usecase.get_by_uuid(project_uuid)

    user = users.get_by_email(user_email)
    has_permission = permissions.can_create_intelligence_in_org(user, org)
    if not has_permission:
        raise IntelligencePermissionDenied()

    integrated_intelligence = IntegratedIntelligence.objects.create(
        intelligence=intelligence, project=project, created_by=user
    )
    return integrated_intelligence


class CreateContentBaseLinkUseCase:
    def __init__(self, event_manager_notify=event_manager.notify):
        self.event_manager_notify = event_manager_notify

    def create_content_base_link(self, content_base_link: ContentBaseLinkDTO) -> ContentBaseLink:
        user = users.get_by_email(content_base_link.user_email)
        content_base = intelligences.get_by_contentbase_uuid(contentbase_uuid=content_base_link.content_base_uuid)
        content_base_link = ContentBaseLink.objects.create(
            link=content_base_link.link, content_base=content_base, created_by=user
        )

        self.event_manager_notify(
            event="contentbase_link_activity", content_base_link=content_base_link, action_type="C", user=user
        )

        return content_base_link


def create_llm(
    llm_dto: LLMDTO,
) -> LLM:
    usecase = projects.ProjectsUseCase()
    project = usecase.get_by_uuid(llm_dto.project_uuid)

    org = project.org
    user = users.get_by_email(llm_dto.user_email)

    has_permission = permissions.can_create_intelligence_in_org(user, org)
    if not has_permission:
        raise IntelligencePermissionDenied()

    intelligence = intelligences.get_integrated_intelligence_by_project(project_uuid=llm_dto.project_uuid)
    llm = LLM.objects.create(
        created_by=user,
        integrated_intelligence=intelligence,
        model=llm_dto.model,
        setup=llm_dto.setup,
        advanced_options=llm_dto.advanced_options,
    )
    return llm


def create_base_integrated_intelligence(
    project: Project, user: User, intelligence: Intelligence
) -> IntegratedIntelligence:
    try:
        return IntegratedIntelligence.objects.create(project=project, intelligence=intelligence, created_by=user)
    except ValidationError as e:
        # Check if this is a router validation error
        if "A project can only have one IntegratedIntelligence with is_router=True" in str(e):
            # Find the existing IntegratedIntelligence with router intelligence
            existing_integrated_intelligence = IntegratedIntelligence.objects.filter(
                project=project, intelligence__is_router=True
            ).first()

            if existing_integrated_intelligence:
                # Check if the existing intelligence is not a router, if so, make it a router
                if not existing_integrated_intelligence.intelligence.is_router:
                    existing_integrated_intelligence.intelligence.is_router = True
                    existing_integrated_intelligence.intelligence.save()
                return existing_integrated_intelligence
            else:
                # If no existing router found, make the current intelligence a router and try again
                intelligence.is_router = True
                intelligence.save()
                integrated_intelligence = IntegratedIntelligence.objects.create(
                    project=project, intelligence=intelligence, created_by=user
                )
                return integrated_intelligence
        else:
            # Re-raise if it's a different validation error
            raise e


def create_base_brain_structure(
    proj: Project,
) -> IntegratedIntelligence:
    org = proj.org
    user = org.created_by

    intelligence = Intelligence.objects.create(name=proj.name, org=org, created_by=user, is_router=True)
    ContentBase.objects.create(title=proj.name, intelligence=intelligence, created_by=user, is_router=True)
    integrated_intelligence = create_base_integrated_intelligence(project=proj, user=user, intelligence=intelligence)
    # TODO: Handle different languages
    LLM.objects.create(
        created_by=user,
        integrated_intelligence=integrated_intelligence,
        setup={
            "version": settings.WENIGPT_DEFAULT_VERSION,
            "temperature": settings.WENIGPT_TEMPERATURE,
            "top_p": settings.WENIGPT_TOP_P,
            "top_k": settings.WENIGPT_TOP_K,
            "max_length": settings.WENIGPT_MAX_LENGHT,
            "language": settings.WENIGPT_DEFAULT_LANGUAGE,
        },
        advanced_options={},
    )
    return integrated_intelligence


class ConversationUseCase:
    def create_conversation_base_structure(
        self,
        project_uuid: str,
        contact_urn: str,
        contact_name: str = "",
        channel_uuid: str = None,
    ) -> Conversation:
        msg_created_at = pendulum.now()

        start_date = pendulum.instance(msg_created_at)
        end_date = start_date.add(days=1)

        conversation = Conversation.objects.create(
            project_id=project_uuid,
            contact_urn=contact_urn,
            start_date=start_date,
            end_date=end_date,
            channel_uuid=channel_uuid,
        )
        if contact_name:
            conversation.contact_name = contact_name
            conversation.save()
        return conversation

    def conversation_in_progress_exists(
        self,
        project_uuid: str,
        channel_uuid: str,
        contact_urn: str,
        contact_name: str,
    ) -> Conversation:
        conversation_queryset = Conversation.objects.filter(
            project_id=project_uuid,
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            resolution=2,
        )

        if not conversation_queryset.exists():
            conversation = self.create_conversation_base_structure(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                contact_name=contact_name,
                channel_uuid=channel_uuid,
            )
            return conversation

        if conversation_queryset.count() > 1:
            conversation_queryset = conversation_queryset.order_by("-created_at")
            conversation_queryset.exclude(uuid=conversation_queryset.first().uuid).update(resolution=3)
            return conversation_queryset.first()

        return conversation_queryset.first()
