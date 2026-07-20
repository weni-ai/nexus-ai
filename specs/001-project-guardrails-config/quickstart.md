# Quickstart: Project Guardrails Configuration (Backend)

```bash
# 1. GET (lazy init)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/$PROJECT_UUID/guardrails-config/" | jq

# 2. Block a category
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": true}}' \
  "http://localhost:8000/api/$PROJECT_UUID/guardrails-config/" | jq

# 3. Unblock a category (persists immediately; FE may show a modal before this call)
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": false}}' \
  "http://localhost:8000/api/$PROJECT_UUID/guardrails-config/" | jq

# 4. Message-only PATCH
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"blocking_message": "I cannot help with that request."}' \
  "http://localhost:8000/api/$PROJECT_UUID/guardrails-config/" | jq

# 5. Inspect persisted config
python manage.py shell -c "
from nexus.projects.models import ProjectGuardrailsConfig
c = ProjectGuardrailsConfig.objects.get(project__uuid='$PROJECT_UUID')
print(c.category_states, c.blocking_message)
"

pytest nexus/projects/api/tests/test_guardrails_config.py nexus/usecases/guardrails/tests/ -q -k guardrail
```
