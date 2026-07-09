# Quickstart: Project Guardrails Configuration (Backend)

```bash
# 1. GET (lazy init)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 2. Block a category
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": true}}' \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 3. Unblock without confirm → 409
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": false}}' \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 4. Unblock with confirm
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_states": {"politics": false}, "confirm_disable": true}' \
  "http://localhost:8000/api/v1/projects/$PROJECT_UUID/guardrails-config/" | jq

# 5. Runtime payload
python manage.py shell -c "
from nexus.usecases.guardrails.guardrails_usecase import GuardrailsUsecase
import json
print(json.dumps(GuardrailsUsecase.get_guardrail_as_dict('$PROJECT_UUID'), indent=2))
"

pytest nexus/projects/api/tests/test_guardrails_config.py nexus/usecases/guardrails/tests/ -q
```
