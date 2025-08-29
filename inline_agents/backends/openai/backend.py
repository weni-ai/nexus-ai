import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List

import pendulum
from agents import Agent, Runner
from django.conf import settings
from redis import Redis

from inline_agents.backend import InlineAgentsBackend
from inline_agents.backends.openai.adapter import (
    OpenAITeamAdapter,
    process_openai_trace,
)
from inline_agents.backends.openai.hooks import SupervisorHooks, RunnerHooks
from inline_agents.backends.openai.sessions import (
    RedisSession,
    make_session_factory,
)
from nexus.inline_agents.backends.openai.models import (
    OpenAISupervisor as Supervisor,
)
from nexus.inline_agents.models import InlineAgentsConfiguration
from nexus.intelligences.models import ContentBase
from nexus.projects.models import Project
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)


@dataclass
class StreamEventCapture:
    timestamp: str
    event_type: str
    event_data: Dict[str, Any]
    agent_name: str = ""


class StreamEventLogger:
    def __init__(self, output_file: str = "stream_events.json"):
        self.output_file = output_file
        self.events: List[StreamEventCapture] = []

    def convert_event(self, event, agent_name: str = ""):
        try:
            event_data = {}

            if hasattr(event, 'type'):
                event_data['type'] = event.type

            if hasattr(event, 'data'):
                event_data['data'] = self._serialize_data(event.data)

            if hasattr(event, 'item'):
                event_data['item'] = self._serialize_data(event.item)

            if hasattr(event, 'name'):
                event_data['name'] = event.name

            if hasattr(event, 'new_agent'):
                event_data['new_agent'] = self._serialize_data(event.new_agent)

            captured_event = StreamEventCapture(
                timestamp=datetime.now().isoformat(),
                event_type=event.type if hasattr(event, 'type') else str(type(event)),
                event_data=event_data,
                agent_name=agent_name
            )
            return captured_event

        except Exception as e:
            print(f"❌ Error capturing event: {e}")

    def _serialize_data(self, data) -> Any:
        try:
            if hasattr(data, '__dict__'):
                return {k: self._serialize_data(v) for k, v in data.__dict__.items()}
            elif isinstance(data, (list, tuple)):
                return [self._serialize_data(item) for item in data]
            elif isinstance(data, dict):
                return {k: self._serialize_data(v) for k, v in data.items()}
            else:
                return str(data)
        except:
            return str(data)

    def save_to_json(self, directory: str = 'events') -> str:
        try:
            events_data = []
            for event in self.events:
                events_data.append(asdict(event))

            os.makedirs(directory, exist_ok=True)

            output_path = os.path.join(directory, os.path.basename(self.output_file))

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(events_data, f, indent=2, ensure_ascii=False)

            print(f"✅ Events saved at: {output_path}")
            return output_path

        except Exception as e:
            print(f"❌ Error saving events: {e}")
            return ""

    def get_events_summary(self) -> Dict[str, Any]:
        event_types = {}
        for event in self.events:
            event_type = event.event_type
            if event_type not in event_types:
                event_types[event_type] = 0
            event_types[event_type] += 1

        return {
            "total_events": len(self.events),
            "event_types": event_types,
            "duration": f"{self.events[-1].timestamp} - {self.events[0].timestamp}" if self.events else "N/A"
        }


class OpenAISupervisorRepository:
    @classmethod
    def get_supervisor(
        cls,
        project: Project,
    ) -> Agent:

        supervisor = Supervisor.objects.order_by('id').last()

        if not supervisor:
            raise Supervisor.DoesNotExist()

        supervisor_dict = {
            "instruction": cls._get_supervisor_instructions(project=project, supervisor=supervisor),
            "tools": cls._get_supervisor_tools(project=project, supervisor=supervisor),
            "foundation_model": supervisor.foundation_model,
            "knowledge_bases": supervisor.knowledge_bases,
            "prompt_override_configuration": supervisor.prompt_override_configuration,
        }

        return supervisor_dict

    @classmethod
    def _get_supervisor_instructions(cls, project, supervisor) -> str:
        if project.use_components and project.human_support:
            return supervisor.components_human_support_prompt
        elif project.use_components:
            return supervisor.components_prompt
        elif project.human_support:
            return supervisor.human_support_prompt
        else:
            return supervisor.instruction

    @classmethod
    def _get_supervisor_tools(cls, project, supervisor) -> list[dict]:
        if project.human_support:
            return supervisor.human_support_action_groups
        return supervisor.action_groups


class OpenAIBackend(InlineAgentsBackend):
    supervisor_repository = OpenAISupervisorRepository
    team_adapter = OpenAITeamAdapter

    def __init__(self):
        super().__init__()
        self._event_manager_notify = None
        self._data_lake_event_adapter = None

    def _get_client(self):
        return Runner()

    def _get_session(self, project_uuid: str, sanitized_urn: str) -> tuple[RedisSession, str]:
        redis_client = Redis.from_url(settings.REDIS_URL)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return RedisSession(session_id=session_id, r=redis_client), session_id

    def _get_session_factory(self, project_uuid: str, sanitized_urn: str):
        redis_client = Redis.from_url(settings.REDIS_URL)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return make_session_factory(redis=redis_client, base_id=session_id)

    def end_session(self, project_uuid: str, sanitized_urn: str):
        session, session_id = self._get_session(project_uuid=project_uuid, sanitized_urn=sanitized_urn)
        session.clear_session()

    def _get_event_manager_notify(self):
        if self._event_manager_notify is None:
            from nexus.events import async_event_manager
            self._event_manager_notify = async_event_manager.notify
        return self._event_manager_notify

    def invoke_agents(
        self,
        team: list[dict],
        input_text: str,
        project_uuid: str,
        sanitized_urn: str,
        contact_fields: str,
        project: Project,
        content_base: ContentBase,
        preview: bool = False,
        language: str = "en",
        contact_name: str = "",
        contact_urn: str = "",
        channel_uuid: str = "",
        use_components: bool = False,
        user_email: str = None,
        rationale_switch: bool = False,
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        event_manager_notify: callable = None,
        inline_agent_configuration: InlineAgentsConfiguration | None = None,
        **kwargs
    ):
        self._event_manager_notify = event_manager_notify or self._get_event_manager_notify()
        session_factory = self._get_session_factory(project_uuid=project_uuid, sanitized_urn=sanitized_urn)
        session, session_id = self._get_session(project_uuid=project_uuid, sanitized_urn=sanitized_urn)

        supervisor: Dict[str, Any] = self.supervisor_repository.get_supervisor(project=project)
        supervisor_hooks = SupervisorHooks(
            supervisor_name="manager",
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            event_manager_notify=self._event_manager_notify,
            agents=team,
        )
        runner_hooks = RunnerHooks(
            supervisor_name="manager",
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            event_manager_notify=self._event_manager_notify,
            agents=team,
        )
        external_team = self.team_adapter.to_external(
            supervisor=supervisor,
            agents=team,
            input_text=input_text,
            project_uuid=project_uuid,
            contact_fields=contact_fields,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            supervisor_hooks=supervisor_hooks,
            runner_hooks=runner_hooks,
            project=project,
            content_base=content_base,
            inline_agent_configuration=inline_agent_configuration,
            session_factory=session_factory,
            session=session,
        )

        client = self._get_client()

        if preview and user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={
                    "type": "status",
                    "content": "Starting OpenAI agent processing",
                    "session_id": session_id
                }
            )

        result = asyncio.run(self._invoke_agents_async(
            client, external_team, session, session_id,
            input_text, contact_urn, project_uuid, channel_uuid,
            user_email, preview, rationale_switch, language,
            turn_off_rationale, msg_external_id, runner_hooks
        ))
        return result

    async def _invoke_agents_async(
        self,
        client,
        external_team,
        session,
        session_id,
        input_text,
        contact_urn,
        project_uuid,
        channel_uuid,
        user_email,
        preview,
        rationale_switch,
        language,
        turn_off_rationale,
        msg_external_id,
        runner_hooks,
    ):
        """Async wrapper to handle the streaming response"""

        event_logger = StreamEventLogger(f"{session_id}{pendulum.now()}.json")

        result = client.run_streamed(**external_team, session=session, hooks=runner_hooks)

        async for event in result.stream_events():
            if event.type == "run_item_stream_event":
                converted_event = event_logger.convert_event(event, agent_name="Supervisor")
                standardized_event = process_openai_trace(asdict(converted_event))

                if event.name == "reasoning_item_created":
                    summaries = event.item.raw_item.summary
                    if summaries:
                        for summary in summaries:
                            trace_data = {
                                "collaboratorName": "",
                                "eventTime": pendulum.now().to_iso8601_string(),
                                "trace": {
                                    "orchestrationTrace": {
                                        "rationale": {
                                            "text": summary.text,
                                            "reasoningId": event.item.raw_item.id
                                        }
                                    }
                                }
                            }
                            standardized_event = {
                                "config": {
                                    "agentName": "",
                                    "type": "thinking",
                                },
                                "trace": trace_data,
                            }
                            await self._event_manager_notify(
                                event="inline_trace_observers_async",
                                inline_traces=standardized_event,
                                user_input=input_text,
                                contact_urn=contact_urn,
                                project_uuid=project_uuid,
                                send_message_callback=None,
                                preview=preview,
                                rationale_switch=rationale_switch,
                                language=language,
                                user_email=user_email,
                                session_id=session_id,
                                msg_external_id=msg_external_id,
                                turn_off_rationale=turn_off_rationale,
                                channel_uuid=channel_uuid
                            )
                            print(f"\n[+] Reasoning: {summary.text}\n")

            elif event.type == "agent_updated_stream_event":
                pass
                # converted_event = event_logger.convert_event(event, agent_name="Supervisor")
                # standardized_event = process_openai_trace(asdict(converted_event))

        return result.final_output
