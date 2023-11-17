from .get_by_uuid import get_by_uuid


class UpdateIntelligenceUseCase():

    def __init__(self):
        pass

    def update_intelligences(
            self,
            intelligence_uuid: str,
            name: str = None,
            description: str = None,
    ):

        intelligence = get_by_uuid(intelligence_uuid)

        if name:
            intelligence.name = name

        if description:
            intelligence.description = description

        intelligence.save()

        return intelligence
