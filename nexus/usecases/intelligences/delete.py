from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid
)


class DeleteIntelligenceUseCase():

    def delete_intelligences(
            self,
            intelligence_uuid: str
    ):

        intelligence = get_by_intelligence_uuid(intelligence_uuid)
        intelligence.delete()
        return True


class DeleteContentBaseUseCase():

    def delete_contentbase(
            self,
            contentbase_uuid: str
    ):

        contentbase = get_by_contentbase_uuid(contentbase_uuid)
        contentbase.delete()
        return True


class DeleteContentBaseTextUseCase():

    def delete_contentbasetext(
            self,
            contentbasetext_uuid: str
    ):

        contentbasetext = get_by_contentbasetext_uuid(contentbasetext_uuid)
        contentbasetext.delete()
        return True
