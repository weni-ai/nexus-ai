from inline_agents.backend import InlineAgentsBackend
from .bedrock.backend import BedrockBackend
from .exceptions import BackendAlreadyRegistered, UnregisteredBackend


class Backends:
    _names = []
    _options = {}
    
    @classmethod
    def register(cls, backend: InlineAgentsBackend):
        backend_name = backend.__class__.__name__

        if cls._options.get(backend_name) is not None:
            raise BackendAlreadyRegistered(f"Backend: {backend_name} is already registered")
        
        cls._options[backend_name] = backend
        cls._names.append(backend_name)

    def get_backend(cls, key: str):
        backend = cls._options.get(key)
        if backend is None:
            raise UnregisteredBackend("Backend with key: abc is not registered")

        return backend


Backends.register(BedrockBackend())
