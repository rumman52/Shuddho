from dataclasses import dataclass

from .auth import JwtVerifier
from .config import Settings
from .database import session_factory
from .repository import Repository
from .storage import make_storage
from .action_repository import ActionRepository
from .actions import ActionService
from .google_actions import GoogleActions
from .agent_repository import AgentRepository
from .memory_repository import MemoryRepository


@dataclass
class Container:
    settings: Settings
    repository: Repository
    storage: object
    verifier: JwtVerifier
    actions: ActionService | None = None
    agent: AgentRepository | None = None
    memory: MemoryRepository | None = None

    def __post_init__(self):
        if self.actions is None:
            self.actions = ActionService(ActionRepository(self.repository.sessions, self.settings), GoogleActions(self.settings))
        if self.agent is None:
            self.agent = AgentRepository(self.repository.sessions, self.settings)
        if self.memory is None:
            self.memory = MemoryRepository(self.repository.sessions, self.settings)

    @classmethod
    def create(cls, settings: Settings):
        settings.validate()
        return cls(settings, Repository(session_factory(settings.database_url), settings),
                   make_storage(settings), JwtVerifier(settings.auth_issuer, settings.auth_audience))
