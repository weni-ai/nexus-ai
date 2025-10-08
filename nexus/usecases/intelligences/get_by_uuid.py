import sentry_sdk

from django.core.exceptions import ValidationError

from .exceptions import (
    IntelligenceDoesNotExist,
    ContentBaseDoesNotExist,
    ContentBaseTextDoesNotExist,
    UserQuestionDoesNotExist,
    ContentBaseFileDoesNotExist,
    ContentBaseLinkDoesNotExist,
)
from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseLogs,
    UserQuestion,
    IntegratedIntelligence,
    LLM
)
from nexus.projects.models import Project
from nexus.inline_agents.models import InlineAgentsConfiguration
from .create import create_base_brain_structure


def get_by_intelligence_uuid(intelligence_uuid: str) -> Intelligence:
    try:
        return Intelligence.objects.get(uuid=intelligence_uuid)
    except (Intelligence.DoesNotExist):
        raise IntelligenceDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_by_contentbase_uuid(contentbase_uuid: str) -> ContentBase:
    try:
        return ContentBase.objects.get(uuid=contentbase_uuid)
    except (ContentBase.DoesNotExist):
        raise ContentBaseDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_by_contentbasetext_uuid(contentbasetext_uuid: str) -> ContentBaseText:
    try:
        return ContentBaseText.objects.get(uuid=contentbasetext_uuid)
    except (ContentBaseText.DoesNotExist):
        raise ContentBaseTextDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_by_content_base_file_uuid(content_base_uuid: str) -> ContentBaseFile:
    try:
        return ContentBaseFile.objects.get(uuid=content_base_uuid)
    except ContentBaseFile.DoesNotExist:
        raise ContentBaseFileDoesNotExist(f"[ ContentBaseFile ] - ContentBaseFile with uuid `{content_base_uuid}` does not exists.")
    except Exception as exception:
        raise (f"[ ContentBaseFile ] - ContentBaseFile error to get - error: `{exception}`")


def get_by_content_base_link_uuid(content_base_uuid: str) -> ContentBaseLink:
    try:
        return ContentBaseLink.objects.get(uuid=content_base_uuid)
    except ContentBaseLink.DoesNotExist:
        raise ContentBaseLinkDoesNotExist(f"[ ContentBaseLink ] - ContentBaseLink with uuid `{content_base_uuid}` does not exists.")
    except Exception as exception:
        raise (f"[ ContentBaseLink ] - ContentBaseFile error to get - error: `{exception}`")


def get_contentbasetext_by_contentbase_uuid(
        content_base_uuid: str
) -> ContentBaseText:
    try:
        return ContentBaseText.objects.get(content_base__uuid=content_base_uuid)
    except (ContentBaseText.DoesNotExist):
        raise ContentBaseTextDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_user_question_by_uuid(user_question_uuid: str):
    try:
        return UserQuestion.objects.get(uuid=user_question_uuid)
    except UserQuestion.DoesNotExist:
        raise UserQuestionDoesNotExist()


def get_log_by_question_uuid(user_question_uuid: str) -> ContentBaseLogs:
    question = get_user_question_by_uuid(user_question_uuid)
    return question.content_base_log


def get_or_create_default_integrated_intelligence_by_project(
    project_uuid: str
) -> IntegratedIntelligence:
    try:
        return IntegratedIntelligence.objects.get(
            project__uuid=project_uuid,
            intelligence__is_router=True
        )
    except IntegratedIntelligence.DoesNotExist:
        project = Project.objects.get(uuid=project_uuid)
        integrated_intelligence = create_base_brain_structure(project)
        return integrated_intelligence
    except IntegratedIntelligence.MultipleObjectsReturned:
        # Get all IntegratedIntelligence objects for this project with is_router=True
        integrated_intelligences = IntegratedIntelligence.objects.filter(
            project__uuid=project_uuid,
            intelligence__is_router=True
        ).order_by("created_at")

        # Get the oldest one (first in the ordered list)
        oldest_integrated_intelligence = integrated_intelligences.first()

        # Get all the duplicates (excluding the oldest one)
        duplicate_integrated_intelligences = integrated_intelligences[1:]

        # Update intelligence__is_router=False and collect IDs for deletion in one loop
        duplicate_ids = []
        for duplicate in duplicate_integrated_intelligences:
            duplicate.intelligence.is_router = False
            duplicate.intelligence.save()
            duplicate_ids.append(duplicate.id)

        # Delete the duplicate IntegratedIntelligence objects
        IntegratedIntelligence.objects.filter(id__in=duplicate_ids).delete()

        return oldest_integrated_intelligence

    except Exception as exception:
        sentry_sdk.capture_exception(exception)
        sentry_sdk.set_tag("project_uuid", project_uuid)
        raise Exception(f"[ Intelligence ] - Intelligence error to get - error: `{exception}`")


def get_integrated_intelligence_by_project(
    project_uuid: str
) -> IntegratedIntelligence:
    try:
        return get_or_create_default_integrated_intelligence_by_project(project_uuid)
    except IntegratedIntelligence.DoesNotExist:
        raise Exception(f"[ IntegratedIntelligence ] - IntegratedIntelligence with project uuid `{project_uuid}` does not exists.")
    except Exception as exception:
        raise Exception(f"[ IntegratedIntelligence ] - IntegratedIntelligence error to get - error: `{exception}`")


def get_default_content_base_by_project(
    project_uuid: str
) -> ContentBase:
    try:
        integrated_intelligence = get_integrated_intelligence_by_project(project_uuid)
        content_bases = integrated_intelligence.intelligence.contentbases.all()
        return content_bases.get(is_router=True)
    except ContentBase.DoesNotExist:
        raise ContentBaseDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_project_and_content_base_data(
    project_uuid: str
) -> tuple[Project, ContentBase, InlineAgentsConfiguration | None]:
    # TODO: optimize queries to avoid N+1
    try:
        inline_agent_configuration = None
        project = Project.objects.select_related('org').get(uuid=project_uuid)

        integrated_intelligence = get_integrated_intelligence_by_project(project_uuid)

        content_base = integrated_intelligence.intelligence.contentbases.select_related(
            'agent'
        ).prefetch_related(
            'instructions'
        ).get(is_router=True)

        if project.agents_backend == "OpenAIBackend":
            # for now we only check for OpenAIBackend
            try:
                inline_agent_configuration = project.inline_agent_configurations.get(agents_backend="OpenAIBackend")
            except InlineAgentsConfiguration.DoesNotExist:
                inline_agent_configuration = None

        return project, content_base, inline_agent_configuration
    except (Project.DoesNotExist, ContentBase.DoesNotExist):
        raise ContentBaseDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_llm_by_project_uuid(
    project_uuid: str
) -> LLM:
    try:
        integrated_intelligence = get_integrated_intelligence_by_project(project_uuid)
        return LLM.objects.get(integrated_intelligence=integrated_intelligence)
    except LLM.DoesNotExist:
        raise Exception(f"[ LLM ] - LLM with project uuid `{project_uuid}` does not exists.")
    except Exception as exception:
        raise Exception(f"[ LLM ] - LLM error to get - error: `{exception}`")
