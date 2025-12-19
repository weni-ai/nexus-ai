from unittest.mock import MagicMock

from router.tasks.tasks import start_route


def test_task_start_message_concatenates_pending_response(monkeypatch):
    # Stub many dependencies to isolate Redis behavior
    class DummyRedis:
        def __init__(self):
            self.store = {}

        def get(self, k):
            v = self.store.get(k)
            return v.encode("utf-8") if isinstance(v, str) else v

        def set(self, k, v):
            self.store[k] = v

        def delete(self, k):
            self.store.pop(k, None)

    dummy_redis = DummyRedis()

    # Patch redis_client in module scope
    monkeypatch.setattr("router.tasks.tasks.Redis", type("R", (), {"from_url": staticmethod(lambda url: dummy_redis)}))
    monkeypatch.setattr(
        "router.tasks.tasks.celery_app", type("C", (), {"control": type("X", (), {"revoke": lambda *a, **k: None})})()
    )

    # Patch repositories, log usecase and llm client related calls minimally
    class StubFlowsRepo:
        def __init__(self, *a, **k):
            pass

        def get_project_flow_by_name(self, name):
            return type("F", (), {"send_to_llm": False, "pk": "pk", "name": "flow"})()

        def project_flow_fallback(self, fallback=True):
            return None

        def get_classifier_flow_by_action_type(self, action_type: str):
            return None

        def project_flows(self, action_type: str, fallback: bool = False):
            return []

    monkeypatch.setattr("router.tasks.tasks.FlowsORMRepository", StubFlowsRepo)

    class StubContentBaseRepo:
        def get_content_base_by_project(self, project_uuid):
            return type("CB", (), {"uuid": "cb"})()

        def get_agent(self, content_base_uuid):
            return type(
                "Agent",
                (),
                {
                    "name": "Doris",
                    "role": "Sales",
                    "personality": "Helpful",
                    "goal": "Sell",
                    "set_default_if_null": lambda self: self,
                },
            )()

        def list_instructions(self, content_base_uuid):
            return [type("Instr", (), {"instruction": "be concise"})()]

    monkeypatch.setattr("router.tasks.tasks.ContentBaseORMRepository", StubContentBaseRepo)

    class StubMessageLogsRepo:
        def list_last_messages(self, project_uuid, contact_urn, limit):
            from router.entities.logs import ContactMessageDTO

            return [
                ContactMessageDTO(
                    text="prev",
                    contact_urn=contact_urn,
                    llm_respose="",
                    content_base_uuid="cb",
                    project_uuid=project_uuid,
                )
            ]

        def list_cached_messages(self, project_uuid, contact_urn):
            return []

    monkeypatch.setattr("router.tasks.tasks.MessageLogsRepository", StubMessageLogsRepo)

    class DummyCreateLogUsecase:
        def __init__(self):
            pass

        def create_message_log(self, text, contact_urn, source):
            return MagicMock(id=1)

        def update_status(self, status, exception_text=None):
            return MagicMock(status=status)

        def update_log_field(self, **kwargs):
            return None

        def send_message(self):
            return None

    monkeypatch.setattr("router.tasks.tasks.CreateLogUsecase", DummyCreateLogUsecase)
    monkeypatch.setattr("router.tasks.tasks.dispatch", lambda *a, **k: None)
    monkeypatch.setattr(
        "router.tasks.tasks.get_llm_by_project_uuid",
        lambda p: type(
            "LLM",
            (),
            {
                "model": "chatgpt",
                "setup": {
                    "version": "gpt-4o-mini",
                    "temperature": "0",
                    "top_k": "1",
                    "top_p": "1",
                    "token": "t",
                    "max_length": "100",
                    "max_tokens": "100",
                    "language": "en",
                },
            },
        )(),
    )
    monkeypatch.setattr("router.tasks.tasks.ChatGPTFunctionClassifier", lambda *a, **k: MagicMock())
    # Ensure llm_client has a prompt attribute used by route.update_log_field
    monkeypatch.setattr(
        "router.tasks.tasks.LLMClient",
        type("LC", (), {"get_by_type": staticmethod(lambda t: [lambda **kw: type("LLM", (), {"prompt": "p"})()])}),
    )
    # Avoid invoking real LLM prompt building by stubbing call_llm directly
    monkeypatch.setattr("router.route.call_llm", lambda *a, **k: "resp")
    # Patch route.get_chunks to return full_page strings to avoid None.replace errors
    monkeypatch.setattr("router.route.get_chunks", lambda indexer, text, content_base_uuid: [{"full_page": "page"}])
    # Prevent DB access from reflection task
    monkeypatch.setattr("router.route.run_reflection_task", type("T", (), {"delay": staticmethod(lambda **kw: None)}))
    # Avoid HTTP calls by stubbing dispatch used inside route
    monkeypatch.setattr("router.route.dispatch", lambda *a, **k: {"type": "broadcast"})

    # Build a minimal message and args
    msg = MagicMock()
    msg.text = "new"
    msg.contact_urn = "u"
    msg.project_uuid = "p"

    # Emulate existing pending response and task id
    dummy_redis.set("response:u", "old")
    dummy_redis.set("task:u", "tid")

    # Execute
    # Patch ProjectsUseCase.get_indexer_database_by_uuid to avoid UUID validation
    monkeypatch.setattr(
        "router.tasks.tasks.ProjectsUseCase",
        type("PU", (), {"get_indexer_database_by_uuid": staticmethod(lambda p: lambda: MagicMock())}),
    )
    start_route.run(
        {
            "project_uuid": "00000000-0000-0000-0000-000000000000",
            "text": msg.text,
            "contact_urn": msg.contact_urn,
            "msg_event": {},
        },
        preview=False,
    )

    # After concatenation, the message.text should be 'old\nnew'
    # After execution, pending response key should be deleted
    assert dummy_redis.get("response:u") is None
