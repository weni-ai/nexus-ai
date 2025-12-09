from django.conf import settings

from inline_agents.backend import InlineAgentsBackend

from .exceptions import BackendAlreadyRegistered, UnregisteredBackend


class BackendsRegistry:
    _default_backend: InlineAgentsBackend | None = None
    _names: list[str] = []
    _options: dict[str, InlineAgentsBackend] = {}

    @classmethod
    def register(cls, backend: InlineAgentsBackend, set_default: bool = False):
        backend_name = backend.name
        if cls._options.get(backend_name) is not None:
            raise BackendAlreadyRegistered(f"Backend: {backend_name} is already registered")
        cls._options[backend_name] = backend
        cls._names.append(backend_name)
        if set_default:
            cls._default_backend = backend

    @classmethod
    def get_default_backend(cls) -> InlineAgentsBackend:
        if cls._default_backend is None:
            raise UnregisteredBackend("No default backend is registered")
        return cls._default_backend

    @classmethod
    def get_backend(cls, key: str) -> InlineAgentsBackend:
        backend = cls._options.get(key)
        if backend is None:
            raise UnregisteredBackend(f"Backend with key: {key} is not registered")
        return backend

    @classmethod
    def get_backend_names(cls) -> list[str]:
        return cls._names


default_backend = getattr(settings, "AGENTS_BACKENDS", "bedrock").lower()

from .bedrock.backend import BedrockBackend

BackendsRegistry.register(BedrockBackend(), set_default=(default_backend == "bedrock"))

from .openai.backend import OpenAIBackend

BackendsRegistry.register(OpenAIBackend(), set_default=(default_backend == "openai"))
