import factory

from nexus.intelligences.models import Intelligence

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class IntelligenceFactory(factory.Factory):
    class Meta:
        model = Intelligence

    name = factory.Sequence(lambda n: 'test%d' % n)
    org = factory.SubFactory(OrgFactory)
    created_by = factory.SubFactory(UserFactory)
    description = factory.Sequence(lambda n: 'test%d' % n)
