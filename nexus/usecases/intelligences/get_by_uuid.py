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
    ContentBaseLogs,
    UserQuestion,
    Prompt
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


def get_prompt_by_uuid(
        prompt_uuid: str
) -> Prompt:
    try:
        return Prompt.objects.get(uuid=prompt_uuid)
    except Prompt.DoesNotExist:
        raise Exception(f"[ Prompt ] - Prompt with uuid `{prompt_uuid}` does not exists.")
    except Exception as exception:
        raise (f"[ Prompt ] - Prompt error to get - error: `{exception}`")
