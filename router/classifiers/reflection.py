from router.classifiers.interfaces import OpenAIClientInterface

from router.classifiers.groundedness import Groundedness


class Reflection:

    """
        Reflection classification will always occur after llm responses are received.
        It should reflect on the overall llm performance and improve the quality of the responses.
    """

    def __init__(
        self,
        chunks_used: list,
        llm_response: str,
        log_usecase,
    ):
        self.chunk_used = chunks_used
        self.llm_response = llm_response
        self.log_usecase = log_usecase

    def classify(self):

        groundedness = Groundedness(
            self.llm_response,
            self.chunk_used,
            self.log_usecase,
        )
        return groundedness.classify()
