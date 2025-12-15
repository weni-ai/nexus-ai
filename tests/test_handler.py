from router.handler import PostMessageHandler


def test_post_message_handler_replaces_escape_sequences():
    handler = PostMessageHandler()
    original = "Line1\\nLine2"
    processed = handler.handle_post_message(final_response=original)
    assert processed == "Line1\nLine2"
