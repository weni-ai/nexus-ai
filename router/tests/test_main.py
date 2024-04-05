import uuid
from fastapi.testclient import TestClient
from router.main import app

from nexus.users.models import User
from nexus.orgs.models import Org
from nexus.projects.models import Project
from nexus.actions.models import Flow
from nexus.intelligences.models import (
    Intelligence, IntegratedIntelligence, ContentBase, ContentBaseAgent, ContentBaseInstruction
)

def clean_db():
    Org.objects.all().delete()
    User.objects.all().delete()
    Flow.objects.all().delete()
    Intelligence.objects.all().delete()
    IntegratedIntelligence.objects.all().delete()
    ContentBase.objects.all().delete()
    Project.objects.all().delete()


def test_messages():
    clean_db()
    user  = User.objects.create(email='test@user.com')

    org = Org.objects.create(created_by=user, name='Test Org')
    project = org.projects.create(uuid="7886d8d1-7bdc-4e85-a7fc-220e2256c11b", name="Test Project", created_by=user)

    intelligence = org.intelligences.create(name="Test Intel", created_by=user)

    integrated_intel = IntegratedIntelligence.objects.create(
        project=project,
        intelligence=intelligence,
        created_by=user,
    )

    content_base = ContentBase.objects.create(
        title='test content base', intelligence=intelligence, created_by=user, is_router=True
    )
    agent = ContentBaseAgent.objects.create(
        name="Doris",
        role="Vendas",
        personality="Criativa",
        goal="",
        content_base=content_base
    )

    flow = Flow.objects.create(
        content_base=content_base,
        uuid=uuid.uuid4(),
        name="Compras",
        prompt="Fluxo de compras de roupas"
    )
    fallback = Flow.objects.create(
        content_base=content_base,
        uuid=uuid.uuid4(),
        name="Fluxo de fallback",
        prompt="Fluxo de fallback",
        fallback=True,
    )

    payload={
        "project_uuid": f"{integrated_intel.project.uuid}",
        "text": "Olá gostaria de comprar uma camiseta",
        "contact_urn": ""
    }

    client = TestClient(app)

    response = client.post('/messages', json=payload)

    assert response.status_code == 200

    payload={
        "project_uuid": f"{integrated_intel.project.uuid}",
        "text": "Olá gostaria de uma indicação de leitura",
        "contact_urn": "telegram:844380532"
    }

    client = TestClient(app)

    response = client.post('/messages', json=payload)

    assert response.status_code == 200