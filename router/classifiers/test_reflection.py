import pytest

from router.classifiers.reflection import Reflection, run_reflection_task


@pytest.mark.django_db
def test_reflection_classify_calls_groundedness(monkeypatch):
    from nexus.logs.models import Message, MessageLog

    msg = Message.objects.create(text="t", contact_urn="u")
    log = MessageLog.objects.create(message=msg, llm_response="resp")

    called = {"count": 0}

    class DummyGroundedness:
        def __init__(self, llm_response, chunks_used, log):
            assert log.id == log.id

        def classify(self):
            called["count"] += 1
            return "ok"

    monkeypatch.setattr("router.classifiers.reflection.Groundedness", DummyGroundedness)

    r = Reflection(chunks_used=["c"], llm_response="resp", message_log_id=log.id)
    assert r.classify() == "ok"
    assert called["count"] == 1


def test_run_reflection_task_delegates_to_reflection(monkeypatch):
    class DummyReflection:
        def __init__(self, chunks_used, llm_response, message_log_id):
            pass

        def classify(self):
            return "ok"

    monkeypatch.setattr("router.classifiers.reflection.Reflection", DummyReflection)
    out = run_reflection_task(chunks_used=["c"], llm_response="resp", message_log_id=1)
    assert out == "ok"
