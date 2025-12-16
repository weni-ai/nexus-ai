from router.indexer import get_chunks


class StubIndexer:
    def __init__(self, status=200, response=None):
        self._status = status
        self._response = response or ["A", "B"]

    def search_data(self, content_base_uuid, text):
        return {"status": self._status, "data": {"response": self._response}}


def test_get_chunks_success():
    idx = StubIndexer(status=200, response=["x", "y"])
    out = get_chunks(idx, "t", "cb")
    assert out == ["x", "y"]


def test_get_chunks_non_200_returns_empty():
    idx = StubIndexer(status=500)
    out = get_chunks(idx, "t", "cb")
    assert out == []
