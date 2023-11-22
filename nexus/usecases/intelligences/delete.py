from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid
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
