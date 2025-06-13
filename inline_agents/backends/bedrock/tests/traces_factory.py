import factory
import uuid
import random
from faker import Faker

faker = Faker()


class ActionGroupTraceFactory(factory.Factory):
    class Meta:
        model = dict

    action_group_name = factory.Faker('word')
    function_name = factory.Faker('word')
    parameter_name = factory.Faker('word')
    parameter_value = factory.Faker('numerify', text='########')
    session_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    trace_id = factory.LazyFunction(lambda: f"{str(uuid.uuid4())}-{random.randint(0, 9)}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return {
            "sessionId": kwargs.get('session_id', cls.session_id),
            "trace": {
                "orchestrationTrace": {
                    "invocationInput": {
                        "actionGroupInvocationInput": {
                            "actionGroupName": kwargs.get('action_group_name', cls.action_group_name),
                            "executionType": "LAMBDA",
                            "function": kwargs.get('function_name', cls.function_name),
                            "parameters": [
                                {
                                    "name": kwargs.get('parameter_name', cls.parameter_name),
                                    "type": "int",
                                    "value": kwargs.get('parameter_value', cls.parameter_value)
                                }
                            ]
                        },
                        "invocationType": "ACTION_GROUP",
                        "traceId": kwargs.get('trace_id', cls.trace_id)
                    }
                }
            }
        }


class AgentCollaborationTraceFactory(factory.Factory):
    class Meta:
        model = dict

    agent_alias_arn = factory.LazyFunction(
        lambda: f"arn:aws:bedrock:us-east-1:{faker.numerify(text='##########')}:agent-alias/INLINE_AGENT/{faker.word()}"
    )
    agent_name = factory.Faker('word')
    input_text = factory.Faker('sentence')
    session_id = factory.LazyFunction(
        lambda: f"project-{str(uuid.uuid4())}-session-tel:{faker.numerify(text='##########')}"
    )
    trace_id = factory.LazyFunction(lambda: f"{str(uuid.uuid4())}-{random.randint(0, 9)}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return {
            "sessionId": kwargs.get('session_id', cls.session_id),
            "trace": {
                "orchestrationTrace": {
                    "invocationInput": {
                        "agentCollaboratorInvocationInput": {
                            "agentCollaboratorAliasArn": kwargs.get('agent_alias_arn', cls.agent_alias_arn),
                            "agentCollaboratorName": kwargs.get('agent_name', cls.agent_name),
                            "input": {
                                "text": kwargs.get('input_text', cls.input_text),
                                "type": "TEXT"
                            }
                        },
                        "invocationType": "AGENT_COLLABORATOR",
                        "traceId": kwargs.get('trace_id', cls.trace_id)
                    }
                }
            }
        }
