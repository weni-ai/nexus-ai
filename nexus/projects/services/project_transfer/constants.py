SCHEMA_VERSION = "1.0"

USER_FK_FIELD_NAMES = frozenset(
    {
        "created_by",
        "modified_by",
        "user",
        "created_by_id",
    }
)

# Models imported with objects.create that have unique_together-style constraints.
IMPORT_UNIQUE_LOOKUPS: dict[str, tuple[str, ...]] = {
    "orgs.OrgAuth": ("user", "org"),
    "inline_agents.IntegratedAgent": ("agent", "project"),
    "inline_agents.InlineAgentsConfiguration": ("project", "agents_backend"),
    "inline_agents.AgentCredential": ("project", "key"),
    "inline_agents.ProjectModelProvider": ("project", "provider"),
    "projects.ProjectApiToken": ("project", "name"),
    "intelligences.ContentBaseAgent": ("content_base",),
}
