class MockZeroShotClient:
    def __init__(self, chatbot_goal, response=None):
        self.chatbot_goal = chatbot_goal
        self.response = response if response is not None else {"other": "other"}

    def fast_predict(self, message, flows_list, language):
        return self.response


class MockFunction:
    def __init__(self, name):
        self.name = name


class MockToolCall:
    def __init__(self, function):
        self.function = function


class MockMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class MockChoice:
    def __init__(self, message):
        self.message = message


class MockResponse:
    def __init__(self, choices):
        self.choices = choices


class MockOpenAIClient:
    def __init__(self, response=None, empty_tool_calls=False):
        if response is None:
            if empty_tool_calls:
                tool_calls = []
            else:
                function = MockFunction("example_function")
                tool_call = MockToolCall(function)
                tool_calls = [tool_call]

            message = MockMessage(tool_calls)
            choice = MockChoice(message)
            response = MockResponse([choice])
        self.response = response

    def chat_completions_create(self, model, messages, tools, tool_choice="auto"):
        return self.response
