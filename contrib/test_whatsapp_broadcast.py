# Paste into Django shell (production):
#   python manage.py shell

from nexus.internals.flows import FlowsRESTClient

project_uuid = "cfe42735-935f-4ef6-9af1-3c6e24e0d5aa"
urns = ["ext:roger.alexandre@vtex.com"]
msg = {"msg": {"text": "Oi! Eu sou a Nic"}}

body = dict(urns=urns, project=project_uuid)
body.update(msg)

print("--- request ---")
print("url: /api/v2/internals/whatsapp_broadcasts")
print("project_uuid:", project_uuid)
print("urns:", urns)
print("body:", body)

response = FlowsRESTClient().whatsapp_broadcast(urns, msg, project_uuid)

print("--- response ---")
print("status:", response.status_code)
print("url:", response.url)
print("elapsed_ms:", int(response.elapsed.total_seconds() * 1000))
print("content_type:", response.headers.get("Content-Type", ""))
print("body:")
print(response.text)
