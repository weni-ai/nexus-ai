import json
import random
import uuid

import factory
import pendulum
from faker import Faker

faker = Faker()


class ActionGroupTraceFactory(factory.Factory):
    class Meta:
        model = dict

    action_group_name = factory.Faker("word")
    function_name = factory.Faker("word")
    parameter_name = factory.Faker("word")
    parameter_value = factory.Faker("numerify", text="########")
    session_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    trace_id = factory.LazyFunction(lambda: f"{str(uuid.uuid4())}-{random.randint(0, 9)}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return {
            "sessionId": kwargs.get("session_id", cls.session_id),
            "trace": {
                "orchestrationTrace": {
                    "invocationInput": {
                        "actionGroupInvocationInput": {
                            "actionGroupName": kwargs.get("action_group_name", cls.action_group_name),
                            "executionType": "LAMBDA",
                            "function": kwargs.get("function_name", cls.function_name),
                            "parameters": [
                                {
                                    "name": kwargs.get("parameter_name", cls.parameter_name),
                                    "type": "int",
                                    "value": kwargs.get("parameter_value", cls.parameter_value),
                                }
                            ],
                        },
                        "invocationType": "ACTION_GROUP",
                        "traceId": kwargs.get("trace_id", cls.trace_id),
                    }
                }
            },
        }


class AgentCollaborationTraceFactory(factory.Factory):
    class Meta:
        model = dict

    agent_alias_arn = factory.LazyFunction(
        lambda: f"arn:aws:bedrock:us-east-1:{faker.numerify(text='##########')}:agent-alias/INLINE_AGENT/{faker.word()}"
    )
    agent_name = factory.Faker("word")
    input_text = factory.Faker("sentence")
    session_id = factory.LazyFunction(
        lambda: f"project-{str(uuid.uuid4())}-session-tel:{faker.numerify(text='##########')}"
    )
    trace_id = factory.LazyFunction(lambda: f"{str(uuid.uuid4())}-{random.randint(0, 9)}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return {
            "sessionId": kwargs.get("session_id", cls.session_id),
            "trace": {
                "orchestrationTrace": {
                    "invocationInput": {
                        "agentCollaboratorInvocationInput": {
                            "agentCollaboratorAliasArn": kwargs.get("agent_alias_arn", cls.agent_alias_arn),
                            "agentCollaboratorName": kwargs.get("agent_name", cls.agent_name),
                            "input": {"text": kwargs.get("input_text", cls.input_text), "type": "TEXT"},
                        },
                        "invocationType": "AGENT_COLLABORATOR",
                        "traceId": kwargs.get("trace_id", cls.trace_id),
                    }
                }
            },
        }


class CustomEventTraceFactory(factory.Factory):
    class Meta:
        model = dict

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return {
            "collaboratorName": "cep_agent",
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": str(uuid.uuid4()),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "actionGroupInvocationOutput": {
                            "metadata": {
                                "clientRequestId": str(uuid.uuid4()),
                                "endTime": pendulum.now().to_iso8601_string(),
                                "startTime": pendulum.now().to_iso8601_string(),
                                "totalTimeMs": random.randint(0, 10000),
                            },
                            "text": """{"cep": "1234",
                                "events": [
                                    {
                                        "event_name": "weni_nexus_data",
                                        "key": "csat",
                                        "value_type": "string",
                                        "value": "protocol_agent_csat",
                                        "metadata": {
                                            "agent_collaboration": {
                                                "resposta": "5"
                                            }
                                        }
                                    }
                                ]
                            }""",
                        },
                        "traceId": str(uuid.uuid4()),
                        "type": "ACTION_GROUP",
                    }
                }
            },
        }


class CSATEventTraceFactory(factory.Factory):
    class Meta:
        model = dict

    csat_value = factory.Iterator(["1", "2", "3", "4", "5"])

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return {
            "collaboratorName": "csat_agent",
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": str(uuid.uuid4()),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "actionGroupInvocationOutput": {
                            "metadata": {
                                "clientRequestId": str(uuid.uuid4()),
                                "endTime": pendulum.now().to_iso8601_string(),
                                "startTime": pendulum.now().to_iso8601_string(),
                                "totalTimeMs": random.randint(0, 10000),
                            },
                            "text": json.dumps(
                                {
                                    "events": [
                                        {
                                            "event_name": "weni_nexus_data",
                                            "key": "weni_csat",
                                            "value_type": "string",
                                            "value": kwargs.get("csat_value", cls.csat_value),
                                            "metadata": {},
                                        }
                                    ]
                                }
                            ),
                        },
                        "traceId": str(uuid.uuid4()),
                        "type": "ACTION_GROUP",
                    }
                }
            },
        }


class NPSEventTraceFactory(factory.Factory):
    class Meta:
        model = dict

    nps_value = factory.Iterator([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return {
            "collaboratorName": "nps_agent",
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": str(uuid.uuid4()),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "actionGroupInvocationOutput": {
                            "metadata": {
                                "clientRequestId": str(uuid.uuid4()),
                                "endTime": pendulum.now().to_iso8601_string(),
                                "startTime": pendulum.now().to_iso8601_string(),
                                "totalTimeMs": random.randint(0, 10000),
                            },
                            "text": json.dumps(
                                {
                                    "events": [
                                        {
                                            "event_name": "weni_nexus_data",
                                            "key": "weni_nps",
                                            "value_type": "string",
                                            "value": kwargs.get("nps_value", cls.nps_value),
                                            "metadata": {},
                                        }
                                    ]
                                }
                            ),
                        },
                        "traceId": str(uuid.uuid4()),
                        "type": "ACTION_GROUP",
                    }
                }
            },
        }
