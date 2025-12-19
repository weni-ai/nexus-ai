from unittest.mock import patch

from router.repositories.dynamo.message import MessageRepository


class FakeTable:
    def __init__(self):
        self.items = []
        self.last_evaluated_key = None

    def put_item(self, Item):
        self.items.append(Item)

    def query(self, **kwargs):
        # Return items in reverse order if ScanIndexForward False
        items = list(self.items)
        if kwargs.get("ScanIndexForward") is False:
            items = list(reversed(items))
        resp = {"Items": items}
        if self.last_evaluated_key:
            resp["LastEvaluatedKey"] = self.last_evaluated_key
        return resp

    def batch_writer(self):
        class BW:
            def __init__(self, outer):
                self.outer = outer

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def delete_item(self, Key):
                self.outer.items = [i for i in self.outer.items if i["message_timestamp"] != Key["message_timestamp"]]

        return BW(self)


@patch("router.repositories.dynamo.message.get_message_table")
def test_storage_and_get_messages(get_table):
    table = FakeTable()
    get_table.return_value.__enter__.return_value = table
    get_table.return_value.__exit__.return_value = False
    repo = MessageRepository()
    repo.storage_message(
        "p",
        "u",
        {"text": "t", "source": "s", "created_at": "2024-01-01T00:00:00Z"},
        channel_uuid="c",
    )
    out = repo.get_messages("p", "u", "c", limit=10)
    assert out["total_count"] == 1
    assert out["items"][0]["text"] == "t"


@patch("router.repositories.dynamo.message.get_message_table")
def test_delete_messages_removes_items(get_table):
    table = FakeTable()
    get_table.return_value.__enter__.return_value = table
    get_table.return_value.__exit__.return_value = False
    repo = MessageRepository()
    repo.storage_message(
        "p",
        "u",
        {"text": "t", "source": "s", "created_at": "2024-01-01T00:00:00Z"},
        channel_uuid="c",
    )
    # Ensure there is one item
    assert len(table.items) == 1
    repo.delete_messages("p", "u", "c")
    assert len(table.items) == 0


@patch("router.repositories.dynamo.message.get_message_table")
def test_get_messages_for_conversation_with_date_filter(get_table):
    table = FakeTable()
    get_table.return_value.__enter__.return_value = table
    get_table.return_value.__exit__.return_value = False
    repo = MessageRepository()
    repo.storage_message(
        "p",
        "u",
        {"text": "t", "source": "s", "created_at": "2024-01-01T00:00:00Z"},
        channel_uuid="c",
    )
    items = repo.get_messages_for_conversation(
        "p", "u", "c", start_date="2024-01-01T00:00:00Z", end_date="2024-01-02T00:00:00Z"
    )
    assert len(items) == 1
