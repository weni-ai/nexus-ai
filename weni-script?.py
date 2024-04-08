from nexus.projects.models import Project
from nexus.orgs.models import Org
from nexus.intelligences.models import IntegratedIntelligence, ContentBaseAgent
from nexus.users.models import User
from nexus.actions.models import Flow
user = User.objects.create(email="alisson.souza@weni.ai")

project_uuid = "04bb7ff7-5acb-4d7e-a112-131765b3ca04"


project_uuid='04bb7ff7-5acb-4d7e-a112-131765b3ca04'
text='quero comprar uma camisa'
contact_urn='telegram:844380532'


org = Org.objects.create(created_by=user, name="org_name")

org.projects.create(uuid=project_uuid, name="Projeto", created_by=user)



project = Project.objects.first()


intel = org.intelligences.create(created_by=user, name="inteligencia")


ii = IntegratedIntelligence.objects.create(
    project=project,
    intelligence=intel,
    created_by=user
)

cb = intel.contentbases.create(
    uuid="0aa8d243-0f99-4c75-8309-21a73d6bd223",
    created_by=user,
    title="Teste router"
)

# name = models.CharField(max_length=255, null=True)
#     role = models.CharField(max_length=255, null=True)
#     personality = models.CharField(max_length=255, null=True)
#     goal = models.TextField()
#     content_base =

cb.is_router = True
cb.save()


agent = ContentBaseAgent.objects.create(
    name="Doris",
    role="Vendas",
    personality="Criativa",
    goal="Vender",
    content_base=cb
)

flow = Flow.objects.create(
    uuid="da2c0365-cabe-410b-bc15-4a42a237d91e",
    name="Teste router",
    prompt="Caso esteja interessado em testar o router",
    content_base=cb
)