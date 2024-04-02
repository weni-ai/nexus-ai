from nexus.orgs.models import Org


class GetOrgByIntelligenceUseCase():

    def get_org_by_intelligence_uuid(
            self,
            intelligence_uuid: str
    ) -> Org:
        org = Org.objects.get(
            intelligences__uuid=intelligence_uuid
        )
        return org

    def get_org_by_contentbase_uuid(
            self,
            contentbase_uuid: str
    ) -> Org:
        org = Org.objects.get(
            intelligences__contentbases__uuid=contentbase_uuid
        )
        return org

    def get_org_by_contentbasetext_uuid(
            self,
            contentbasetext_uuid: str
    ) -> Org:
        org = Org.objects.get(
            intelligences__contentbases__contentbasetexts__uuid=contentbasetext_uuid
        )
        return org

    def get_org_by_contentbasefile_uuid(
            self,
            contentbasefile_uuid: str
    ) -> Org:
        org = Org.objects.get(
            intelligences__contentbases__contentbasefiles__uuid=contentbasefile_uuid
        )
        return org


    def get_org_by_project_uuid(
            self,
            project_uuid: str
    ) -> Org:
        org = Org.objects.get(
            projects__uuid=project_uuid


    def get_org_by_contentbaselink_uuid(
            self,
            contentbaselink_uuid: str
    ) -> Org:
        org = Org.objects.get(
            intelligences__contentbases__contentbaselinks__uuid=contentbaselink_uuid
        )
        return org
