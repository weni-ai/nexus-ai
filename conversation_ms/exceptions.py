class ConversationMSException(Exception):
    pass


class ConversationNotFoundError(ConversationMSException):
    pass


class MessageProcessingError(ConversationMSException):
    pass


class InvalidEventDataError(ConversationMSException):
    pass
