import sentry_sdk

_FLOWS_RESPONSE_BODY_LIMIT = 2000


class UnableToSendMessage(Exception):
    pass


def raise_unable_to_send_from_response(error: Exception, response, **context) -> None:
    """Re-raise UnableToSendMessage with the HTTP body attached for Sentry."""
    response_body = (getattr(response, "text", None) or "")[:_FLOWS_RESPONSE_BODY_LIMIT]
    sentry_sdk.set_context(
        "flows_response",
        {
            "status_code": getattr(response, "status_code", None),
            "url": getattr(response, "url", ""),
            "response_body": response_body,
            **{key: value for key, value in context.items() if value is not None},
        },
    )
    raise UnableToSendMessage(f"{error} response_body={response_body}") from error
