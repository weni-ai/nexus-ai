from django.core.exceptions import ValidationError

from .exceptions import (
    IntelligenceDoesNotExist,
    ContentBaseDoesNotExist,
    ContentBaseTextDoesNotExist,
    UserQuestionDoesNotExist
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
        raise Exception(f"[ ContentBaseFile ] - ContentBaseFile with uuid `{content_base_uuid}` does not exists.")
    except Exception as exception:
        raise (f"[ ContentBaseFile ] - ContentBaseFile error to get - error: `{exception}`")


def get_by_content_base_link_uuid(content_base_uuid: str) -> ContentBaseFile:
    try:
        return ContentBaseLink.objects.get(uuid=content_base_uuid)
    except ContentBaseLink.DoesNotExist:
        raise Exception(f"[ ContentBaseLink ] - ContentBaseLink with uuid `{content_base_uuid}` does not exists.")
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


def get_integretade_intelligence_by_project(
    project_uuid: str
) -> IntegratedIntelligence:
    try:
        return IntegratedIntelligence.objects.get(project__uuid=project_uuid)
    except IntegratedIntelligence.DoesNotExist:
        raise Exception(f"[ IntegratedIntelligence ] - IntegratedIntelligence with project uuid `{project_uuid}` does not exists.")
    except Exception as exception:
        raise Exception(f"[ IntegratedIntelligence ] - IntegratedIntelligence error to get - error: `{exception}`")


def get_default_content_base_by_project(
    project_uuid: str
) -> ContentBase:
    try:
        integrated_intelligence = get_integretade_intelligence_by_project(project_uuid)
        content_bases = integrated_intelligence.intelligence.contentbases.all()
        return content_bases.get(is_router=True)
    except ContentBase.DoesNotExist:
        raise ContentBaseDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_llm_by_project_uuid(
    project_uuid: str
) -> LLM:
    try:
        integrated_intelligence = get_integretade_intelligence_by_project(project_uuid)
        return LLM.objects.get(intelligence=integrated_intelligence)
    except LLM.DoesNotExist:
        raise Exception(f"[ LLM ] - LLM with project uuid `{project_uuid}` does not exists.")
    except Exception as exception:
        raise Exception(f"[ LLM ] - LLM error to get - error: `{exception}`")
