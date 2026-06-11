from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.db import models
from django.db.models import QuerySet

from nexus.actions.models import Flow, TemplateAction
from nexus.inline_agents.backends.openai.models import ManagerAgent, ModelProvider, ProjectModelProvider
from nexus.inline_agents.models import (
    Agent,
    AgentCategory,
    AgentCredential,
    AgentGroup,
    AgentGroupModal,
    AgentSystem,
    AgentType,
    ContactField,
    Guardrail,
    InlineAgentMessage,
    InlineAgentsConfiguration,
    IntegratedAgent,
    MCP,
    MCPCredentialTemplate,
    MCPConfigOption,
    Version,
)
from nexus.intelligences.models import (
    LLM,
    ContentBase,
    ContentBaseAgent,
    ContentBaseFile,
    ContentBaseInstruction,
    ContentBaseLink,
    ContentBaseLogs,
    ContentBaseText,
    Conversation,
    IntegratedIntelligence,
    Intelligence,
    SubTopics,
    Topics,
    UserQuestion,
)
from nexus.logs.models import Message, MessageLog, RecentActivities
from nexus.orgs.models import Org, OrgAuth
from nexus.projects.models import (
    Channel,
    IntegratedFeature,
    Project,
    ProjectApiToken,
    ProjectAuth,
    TemplateType,
)
from nexus.task_managers.models import (
    ContentBaseFileTaskManager,
    ContentBaseLinkTaskManager,
    ContentBaseTextTaskManager,
)


@dataclass
class TransferSpec:
    label: str
    model: type[models.Model]
    collect: Callable[[Project], QuerySet]
    export_id: Callable[[models.Model], str]
    import_order: int
    is_catalog: bool = False
    m2m_fields: list[str] = field(default_factory=list)
    import_overrides: dict[str, Any] = field(default_factory=dict)


def _content_base_ids(project: Project) -> QuerySet:
    intelligence_ids = IntegratedIntelligence.objects.filter(project=project).values_list("intelligence_id", flat=True)
    return ContentBase.objects.filter(intelligence_id__in=intelligence_ids).values_list("pk", flat=True)


def _agent_qs(project: Project) -> QuerySet:
    return Agent.objects.filter(project=project)


def _export_uuid(instance: models.Model) -> str:
    return str(instance.uuid)


def _export_slug(instance: models.Model) -> str:
    return instance.slug


def _export_guardrail(instance: models.Model) -> str:
    return f"{instance.identifier}:{instance.version}"


def _export_version(instance: models.Model) -> str:
    return f"{instance.agent.uuid}:{instance.created_on.isoformat()}"


def _export_integrated_agent(instance: models.Model) -> str:
    return f"{instance.agent.uuid}:{instance.project.uuid}"


def _export_agent_credential(instance: models.Model) -> str:
    return f"{instance.project.uuid}:{instance.key or instance.pk}"


def _export_contact_field(instance: models.Model) -> str:
    return f"{instance.agent.uuid}:{instance.key}"


def _export_inline_config(instance: models.Model) -> str:
    return f"{instance.project.uuid}:{instance.agents_backend}"


def _export_content_base_instruction(instance: models.Model) -> str:
    return f"{instance.content_base.uuid}:{hash(instance.instruction)}"


def _export_content_base_logs(instance: models.Model) -> str:
    content_base_uuid = instance.content_base.uuid if instance.content_base else "none"
    return f"{content_base_uuid}:{instance.created_at.isoformat()}:{hash(instance.question)}"


def _export_message_log(instance: models.Model) -> str:
    return str(instance.message.uuid)


def _export_org_auth(instance: models.Model) -> str:
    return f"{instance.org.uuid}:{instance.user.email}"


def _export_mcp_config_option(instance: models.Model) -> str:
    return f"{instance.mcp.slug}:{instance.name}"


def _export_mcp_credential_template(instance: models.Model) -> str:
    return f"{instance.mcp.slug}:{instance.name}"


def _export_agent_group_modal(instance: models.Model) -> str:
    return f"group:{instance.group.slug}"


def _export_template_type(instance: models.Model) -> str:
    if instance.uuid:
        return str(instance.uuid)
    return f"name:{instance.name}"


def _export_content_base_agent(instance: models.Model) -> str:
    return str(instance.content_base.uuid)


def _collect_org(project: Project) -> QuerySet:
    return Org.objects.filter(pk=project.org_id)


def _collect_org_auth(project: Project) -> QuerySet:
    return OrgAuth.objects.filter(org_id=project.org_id)


def _collect_intelligences(project: Project) -> QuerySet:
    intelligence_ids = IntegratedIntelligence.objects.filter(project=project).values_list("intelligence_id", flat=True)
    return Intelligence.objects.filter(pk__in=intelligence_ids)


def _collect_integrated_intelligences(project: Project) -> QuerySet:
    return IntegratedIntelligence.objects.filter(project=project)


def _collect_llms(project: Project) -> QuerySet:
    integrated_ids = IntegratedIntelligence.objects.filter(project=project).values_list("pk", flat=True)
    return LLM.objects.filter(integrated_intelligence_id__in=integrated_ids)


def _collect_content_bases(project: Project) -> QuerySet:
    intelligence_ids = IntegratedIntelligence.objects.filter(project=project).values_list("intelligence_id", flat=True)
    return ContentBase.objects.filter(intelligence_id__in=intelligence_ids)


def _collect_content_base_files(project: Project) -> QuerySet:
    return ContentBaseFile.objects.filter(content_base_id__in=_content_base_ids(project))


def _collect_content_base_links(project: Project) -> QuerySet:
    return ContentBaseLink.objects.filter(content_base_id__in=_content_base_ids(project))


def _collect_content_base_texts(project: Project) -> QuerySet:
    return ContentBaseText.objects.filter(content_base_id__in=_content_base_ids(project))


def _collect_content_base_agents(project: Project) -> QuerySet:
    return ContentBaseAgent.objects.filter(content_base_id__in=_content_base_ids(project))


def _collect_content_base_instructions(project: Project) -> QuerySet:
    return ContentBaseInstruction.objects.filter(content_base_id__in=_content_base_ids(project))


def _collect_content_base_logs(project: Project) -> QuerySet:
    return ContentBaseLogs.objects.filter(content_base_id__in=_content_base_ids(project))


def _collect_user_questions(project: Project) -> QuerySet:
    log_ids = ContentBaseLogs.objects.filter(content_base_id__in=_content_base_ids(project)).values_list("pk", flat=True)
    return UserQuestion.objects.filter(content_base_log_id__in=log_ids)


def _collect_flows(project: Project) -> QuerySet:
    return Flow.objects.filter(content_base_id__in=_content_base_ids(project))


def _collect_template_actions(project: Project) -> QuerySet:
    template_ids = (
        Flow.objects.filter(content_base_id__in=_content_base_ids(project))
        .exclude(action_template_id__isnull=True)
        .values_list("action_template_id", flat=True)
    )
    return TemplateAction.objects.filter(pk__in=template_ids)


def _collect_template_type(project: Project) -> QuerySet:
    if project.template_type_id is None:
        return TemplateType.objects.none()
    return TemplateType.objects.filter(pk=project.template_type_id)


def _collect_guardrail(project: Project) -> QuerySet:
    if project.guardrail_id is None:
        return Guardrail.objects.none()
    return Guardrail.objects.filter(pk=project.guardrail_id)


def _collect_manager_agents(project: Project) -> QuerySet:
    manager_ids: set[int] = set()
    if project.manager_agent_id:
        manager_ids.add(project.manager_agent_id)
    provider_ids = ProjectModelProvider.objects.filter(project=project).values_list("provider_id", flat=True)
    manager_ids.update(
        ModelProvider.objects.filter(pk__in=provider_ids)
        .exclude(manager_agent_id__isnull=True)
        .values_list("manager_agent_id", flat=True)
    )
    if not manager_ids:
        return ManagerAgent.objects.none()
    return ManagerAgent.objects.filter(pk__in=manager_ids)


def _collect_model_providers(project: Project) -> QuerySet:
    provider_ids = ProjectModelProvider.objects.filter(project=project).values_list("provider_id", flat=True)
    return ModelProvider.objects.filter(pk__in=provider_ids)


def _collect_agent_types(project: Project) -> QuerySet:
    type_ids = _agent_qs(project).exclude(agent_type_id__isnull=True).values_list("agent_type_id", flat=True)
    return AgentType.objects.filter(pk__in=type_ids)


def _collect_agent_categories(project: Project) -> QuerySet:
    category_ids = _agent_qs(project).exclude(category_id__isnull=True).values_list("category_id", flat=True)
    return AgentCategory.objects.filter(pk__in=category_ids)


def _collect_agent_groups(project: Project) -> QuerySet:
    group_ids = _agent_qs(project).exclude(group_id__isnull=True).values_list("group_id", flat=True)
    return AgentGroup.objects.filter(pk__in=group_ids)


def _collect_agent_systems(project: Project) -> QuerySet:
    system_ids = AgentSystem.objects.filter(agents__project=project).values_list("pk", flat=True).distinct()
    return AgentSystem.objects.filter(pk__in=system_ids)


def _collect_mcps(project: Project) -> QuerySet:
    mcp_ids = MCP.objects.filter(agents__project=project).values_list("pk", flat=True).distinct()
    group_mcp_ids = MCP.objects.filter(groups__agents__project=project).values_list("pk", flat=True).distinct()
    return MCP.objects.filter(pk__in=set(mcp_ids) | set(group_mcp_ids))


def _collect_mcp_config_options(project: Project) -> QuerySet:
    mcp_ids = _collect_mcps(project).values_list("pk", flat=True)
    return MCPConfigOption.objects.filter(mcp_id__in=mcp_ids)


def _collect_mcp_credential_templates(project: Project) -> QuerySet:
    mcp_ids = _collect_mcps(project).values_list("pk", flat=True)
    return MCPCredentialTemplate.objects.filter(mcp_id__in=mcp_ids)


def _collect_agent_group_modals(project: Project) -> QuerySet:
    group_ids = _collect_agent_groups(project).values_list("pk", flat=True)
    return AgentGroupModal.objects.filter(group_id__in=group_ids)


def _collect_message_logs(project: Project) -> QuerySet:
    return MessageLog.objects.filter(project=project).select_related("message")


def _collect_messages(project: Project) -> QuerySet:
    message_ids = MessageLog.objects.filter(project=project).values_list("message_id", flat=True)
    return Message.objects.filter(pk__in=message_ids)


def _collect_file_task_managers(project: Project) -> QuerySet:
    file_ids = ContentBaseFile.objects.filter(content_base_id__in=_content_base_ids(project)).values_list("pk", flat=True)
    return ContentBaseFileTaskManager.objects.filter(content_base_file_id__in=file_ids)


def _collect_text_task_managers(project: Project) -> QuerySet:
    text_ids = ContentBaseText.objects.filter(content_base_id__in=_content_base_ids(project)).values_list("pk", flat=True)
    return ContentBaseTextTaskManager.objects.filter(content_base_text_id__in=text_ids)


def _collect_link_task_managers(project: Project) -> QuerySet:
    link_ids = ContentBaseLink.objects.filter(content_base_id__in=_content_base_ids(project)).values_list("pk", flat=True)
    return ContentBaseLinkTaskManager.objects.filter(content_base_link_id__in=link_ids)


TRANSFER_SPECS: list[TransferSpec] = [
    TransferSpec("projects.TemplateType", TemplateType, _collect_template_type, _export_template_type, 10, True),
    TransferSpec("inline_agents.Guardrail", Guardrail, _collect_guardrail, _export_guardrail, 11, True),
    TransferSpec("inline_agents.ManagerAgent", ManagerAgent, _collect_manager_agents, _export_uuid, 12, True),
    TransferSpec("inline_agents.ModelProvider", ModelProvider, _collect_model_providers, _export_uuid, 13, True),
    TransferSpec("inline_agents.AgentType", AgentType, _collect_agent_types, _export_slug, 14, True),
    TransferSpec("inline_agents.AgentCategory", AgentCategory, _collect_agent_categories, _export_slug, 15, True),
    TransferSpec("inline_agents.AgentSystem", AgentSystem, _collect_agent_systems, _export_slug, 16, True),
    TransferSpec("inline_agents.MCP", MCP, _collect_mcps, _export_slug, 17, True, m2m_fields=[]),
    TransferSpec(
        "inline_agents.MCPConfigOption",
        MCPConfigOption,
        _collect_mcp_config_options,
        _export_mcp_config_option,
        18,
        True,
    ),
    TransferSpec(
        "inline_agents.MCPCredentialTemplate",
        MCPCredentialTemplate,
        _collect_mcp_credential_templates,
        _export_mcp_credential_template,
        19,
        True,
    ),
    TransferSpec("inline_agents.AgentGroup", AgentGroup, _collect_agent_groups, _export_slug, 20, True, m2m_fields=["mcps"]),
    TransferSpec(
        "inline_agents.AgentGroupModal",
        AgentGroupModal,
        _collect_agent_group_modals,
        _export_agent_group_modal,
        21,
        True,
    ),
    TransferSpec("actions.TemplateAction", TemplateAction, _collect_template_actions, _export_uuid, 22, True),
    TransferSpec("orgs.Org", Org, _collect_org, _export_uuid, 100),
    TransferSpec("orgs.OrgAuth", OrgAuth, _collect_org_auth, _export_org_auth, 110),
    TransferSpec("intelligences.Intelligence", Intelligence, _collect_intelligences, _export_uuid, 200),
    TransferSpec("projects.Project", Project, lambda p: Project.objects.filter(pk=p.pk), _export_uuid, 210),
    TransferSpec(
        "intelligences.IntegratedIntelligence",
        IntegratedIntelligence,
        _collect_integrated_intelligences,
        _export_uuid,
        220,
    ),
    TransferSpec("intelligences.LLM", LLM, _collect_llms, _export_uuid, 230),
    TransferSpec("intelligences.ContentBase", ContentBase, _collect_content_bases, _export_uuid, 300),
    TransferSpec("intelligences.ContentBaseFile", ContentBaseFile, _collect_content_base_files, _export_uuid, 310),
    TransferSpec("intelligences.ContentBaseLink", ContentBaseLink, _collect_content_base_links, _export_uuid, 320),
    TransferSpec("intelligences.ContentBaseText", ContentBaseText, _collect_content_base_texts, _export_uuid, 330),
    TransferSpec(
        "intelligences.ContentBaseAgent",
        ContentBaseAgent,
        _collect_content_base_agents,
        _export_content_base_agent,
        340,
    ),
    TransferSpec(
        "intelligences.ContentBaseInstruction",
        ContentBaseInstruction,
        _collect_content_base_instructions,
        _export_content_base_instruction,
        350,
    ),
    TransferSpec(
        "intelligences.ContentBaseLogs",
        ContentBaseLogs,
        _collect_content_base_logs,
        _export_content_base_logs,
        360,
    ),
    TransferSpec("intelligences.UserQuestion", UserQuestion, _collect_user_questions, _export_uuid, 370),
    TransferSpec("actions.Flow", Flow, _collect_flows, _export_uuid, 400),
    TransferSpec("inline_agents.Agent", Agent, _agent_qs, _export_uuid, 600, m2m_fields=["systems", "mcps"]),
    TransferSpec("inline_agents.Version", Version, lambda p: Version.objects.filter(agent__project=p), _export_version, 610),
    TransferSpec(
        "inline_agents.IntegratedAgent",
        IntegratedAgent,
        lambda p: IntegratedAgent.objects.filter(project=p),
        _export_integrated_agent,
        620,
    ),
    TransferSpec(
        "inline_agents.ContactField",
        ContactField,
        lambda p: ContactField.objects.filter(project=p),
        _export_contact_field,
        630,
    ),
    TransferSpec(
        "inline_agents.AgentCredential",
        AgentCredential,
        lambda p: AgentCredential.objects.filter(project=p),
        _export_agent_credential,
        640,
        m2m_fields=["agents"],
    ),
    TransferSpec(
        "inline_agents.InlineAgentsConfiguration",
        InlineAgentsConfiguration,
        lambda p: InlineAgentsConfiguration.objects.filter(project=p),
        _export_inline_config,
        650,
    ),
    TransferSpec(
        "inline_agents.ProjectModelProvider",
        ProjectModelProvider,
        lambda p: ProjectModelProvider.objects.filter(project=p),
        _export_uuid,
        660,
    ),
    TransferSpec("projects.Channel", Channel, lambda p: Channel.objects.filter(project=p), lambda i: str(i.uuid), 700),
    TransferSpec(
        "projects.IntegratedFeature",
        IntegratedFeature,
        lambda p: IntegratedFeature.objects.filter(project=p),
        lambda i: f"{i.project.uuid}:{i.feature_uuid}",
        710,
    ),
    TransferSpec("projects.ProjectAuth", ProjectAuth, lambda p: ProjectAuth.objects.filter(project=p), lambda i: f"{i.project.uuid}:{i.user.email}", 720),
    TransferSpec(
        "projects.ProjectApiToken",
        ProjectApiToken,
        lambda p: ProjectApiToken.objects.filter(project=p),
        lambda i: f"{i.project.uuid}:{i.name}",
        730,
        import_overrides={"enabled": False},
    ),
    TransferSpec("intelligences.Topics", Topics, lambda p: Topics.objects.filter(project=p), _export_uuid, 740),
    TransferSpec("intelligences.SubTopics", SubTopics, lambda p: SubTopics.objects.filter(topic__project=p), _export_uuid, 750),
    TransferSpec("intelligences.Conversation", Conversation, lambda p: Conversation.objects.filter(project=p), _export_uuid, 760),
    TransferSpec(
        "inline_agents.InlineAgentMessage",
        InlineAgentMessage,
        lambda p: InlineAgentMessage.objects.filter(project=p),
        _export_uuid,
        770,
    ),
    TransferSpec("logs.Message", Message, _collect_messages, _export_uuid, 800),
    TransferSpec("logs.MessageLog", MessageLog, _collect_message_logs, _export_message_log, 810),
    TransferSpec("logs.RecentActivities", RecentActivities, lambda p: RecentActivities.objects.filter(project=p), _export_uuid, 820),
    TransferSpec(
        "task_managers.ContentBaseFileTaskManager",
        ContentBaseFileTaskManager,
        _collect_file_task_managers,
        _export_uuid,
        830,
    ),
    TransferSpec(
        "task_managers.ContentBaseTextTaskManager",
        ContentBaseTextTaskManager,
        _collect_text_task_managers,
        _export_uuid,
        840,
    ),
    TransferSpec(
        "task_managers.ContentBaseLinkTaskManager",
        ContentBaseLinkTaskManager,
        _collect_link_task_managers,
        _export_uuid,
        850,
    ),
]


def get_unique_specs() -> list[TransferSpec]:
    seen: set[tuple[str, int]] = set()
    unique: list[TransferSpec] = []
    for spec in sorted(TRANSFER_SPECS, key=lambda item: item.import_order):
        key = (spec.label, spec.import_order)
        if key in seen:
            continue
        seen.add(key)
        unique.append(spec)
    return unique


def get_spec_for_model(model: type[models.Model]) -> TransferSpec | None:
    label = model._meta.label
    matches = [spec for spec in TRANSFER_SPECS if spec.label == label]
    if not matches:
        return None
    return matches[0]


def get_spec_by_label(label: str) -> TransferSpec | None:
    matches = [spec for spec in TRANSFER_SPECS if spec.label == label]
    return matches[0] if matches else None
