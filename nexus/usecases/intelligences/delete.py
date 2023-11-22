from .get_by_uuid import get_by_intelligence_uuid


class DeleteIntelligenceUseCase():

    def delete_intelligences(
            self,
            intelligence_uuid: str
    ):

        intelligence = get_by_intelligence_uuid(intelligence_uuid)
        intelligence.delete()
        return True
