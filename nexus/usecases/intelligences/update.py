from .get_by_uuid import get_by_intelligence_uuid, get_by_contentbase_uuid


class UpdateIntelligenceUseCase():

    def __init__(self):
        pass

    def update_intelligences(
            self,
            intelligence_uuid: str,
            name: str = None,
            description: str = None,
    ):

        intelligence = get_by_intelligence_uuid(intelligence_uuid)

        if name:
            intelligence.name = name

        if description:
            intelligence.description = description

        intelligence.save()

        return intelligence


class UpdateContentBaseUseCase():

    def __init__(self):
        pass

    def update_contentbase(
            self,
            contentbase_uuid: str,
            title: str = None,
    ):

        contentbase = get_by_contentbase_uuid(contentbase_uuid)

        if title:
            contentbase.title = title

        contentbase.save()

        return contentbase
