# Quickstart: Project Guardrails Configuration (Backend)

```bash
# 1. GET (lazy init)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 2. Block a category (persists + syncs Bedrock Denied Topics subset)
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": true}}' \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 3. Unblock without confirm → 409
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": false}}' \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 4. Unblock with confirm (sync omits category from Bedrock)
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": false}, "confirm_disable": true}' \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 5. Message-only PATCH (no Bedrock version bump)
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"blocking_message": "I cannot help with that request."}' \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 6. Inspect persisted Bedrock ids + effective message
python manage.py shell -c "
from nexus.projects.models import ProjectGuardrailsConfig
c = ProjectGuardrailsConfig.objects.get(project__uuid='$PROJECT_UUID')
print(c.bedrock_guardrail_identifier, c.bedrock_guardrail_version, c.blocking_message)
"

# 7. Runtime: send a user message that hits a blocked category and confirm
#    the reply is the project message (Option A), not Bedrock canned text.
#    Ensure preprocess does not call GUARDRAILS_LAYER_LAMBDA.

pytest nexus/projects/api/tests/test_guardrails_config.py nexus/usecases/guardrails/tests/ router/tasks/tests/ -q -k guardrail
```
