from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid
)


class RetrieveIntelligenceUseCase():

    def get_intelligence(self, intelligence_uuid: str):
        return get_by_intelligence_uuid(intelligence_uuid)


class RetrieveContentBaseUseCase():

    def get_contentbase(self, contentbase_uuid: str):
        return get_by_contentbase_uuid(contentbase_uuid)


class RetrieveContentBaseTextUseCase():

    def get_contentbasetext(self, contentbasetext_uuid: str):
        return get_by_contentbasetext_uuid(contentbasetext_uuid)
