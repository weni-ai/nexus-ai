import factory

from nexus.orgs.models import Org, OrgAuth, Role
from nexus.usecases.users.tests.user_factory import UserFactory


class OrgFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Org

    name = factory.Sequence(lambda n: "test%d" % n)
    created_by = factory.SubFactory(UserFactory)
    org_auth = factory.RelatedFactory(
        "nexus.usecases.orgs.tests.org_factory.OrgAuthFactory", "org", user=factory.SelfAttribute("..created_by")
    )


class OrgAuthFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrgAuth

    org = factory.SubFactory(OrgFactory)
    user = factory.SubFactory(UserFactory)
    role = Role.ADMIN.value
