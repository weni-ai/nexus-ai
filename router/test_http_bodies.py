from router.http_bodies import MessageHTTPBody


def test_message_http_body_dict_excludes_none_values_and_keeps_present_fields():
    body = MessageHTTPBody(
        project_uuid="p",
        text="hello",
        contact_urn="urn",
        channel_uuid=None,
        contact_name=None,
        metadata={"a": 1},
        attachments=[],
        msg_event={},
        contact_fields={},
    )
    d = body.dict()
    assert "project_uuid" in d and d["project_uuid"] == "p"
    assert "text" in d and d["text"] == "hello"
    assert "contact_urn" in d and d["contact_urn"] == "urn"
    assert "channel_uuid" not in d
    assert "contact_name" not in d
    assert "metadata" in d and d["metadata"] == {"a": 1}
    assert "attachments" in d and d["attachments"] == []
    assert "msg_event" in d and d["msg_event"] == {}
    assert "contact_fields" in d and d["contact_fields"] == {}
