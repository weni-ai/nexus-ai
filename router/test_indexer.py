def test_get_chunks_returns_response_data_when_status_200():
    class FakeIndexer:
        def search_data(self, content_base_uuid: str, text: str):
            return {"status": 200, "data": {"response": ["a", "b"]}}

    chunks = __import__("router.indexer").indexer.get_chunks(FakeIndexer(), "q", "cb")
    assert chunks == ["a", "b"]
