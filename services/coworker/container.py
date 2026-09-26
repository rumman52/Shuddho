from dataclasses import dataclass

from .auth import JwtVerifier
from .config import Settings
from .database import session_factory
from .repository import Repository
from .storage import make_storage
from .action_repository import ActionRepository
from .actions import ActionService
from .permission_gateway import PermissionGateway
from .credential_broker import CredentialBroker
from .google_actions import GoogleActions
from .microsoft_actions import MicrosoftActions
from .linkedin_actions import LinkedInActions
from .agent_repository import AgentRepository
from .goal_repository import GoalRepository
from .automation_repository import AutomationRepository
from .memory_repository import MemoryRepository
from .context import ContextService
from .recipient_repository import RecipientRepository
from .retention import RetentionService


@dataclass
class Container:
    settings: Settings
    repository: Repository
    storage: object
    verifier: JwtVerifier
    actions: ActionService | None = None
    permissions: PermissionGateway | None = None
    credentials: CredentialBroker | None = None
    agent: AgentRepository | None = None
    goals: GoalRepository | None = None
    automations: AutomationRepository | None = None
    memory: MemoryRepository | None = None
    context: ContextService | None = None
    recipients: RecipientRepository | None = None
    retention: RetentionService | None = None

    def __post_init__(self):
        if self.actions is None:
            providers = {"google": GoogleActions(self.settings)}
            if self.settings.microsoft_actions_enabled:
                providers["microsoft"] = MicrosoftActions(self.settings)
            if self.settings.action_social_publishing_enabled:
                providers["linkedin"] = LinkedInActions(self.settings)
            action_repository = ActionRepository(
                self.repository.sessions,
                self.settings,
            )
            if self.permissions is None:
                self.permissions = PermissionGateway(
                    self.repository.sessions,
                    self.settings,
                )
            if self.credentials is None:
                self.credentials = CredentialBroker(
                    action_repository,
                    self.permissions,
                    providers,
                )
            self.actions = ActionService(
                action_repository,
                providers,
                self.storage,
                permission_gateway=self.permissions,
                credential_broker=self.credentials,
            )
        if self.agent is None:
            self.agent = AgentRepository(self.repository.sessions, self.settings)
        if self.goals is None:
            self.goals = GoalRepository(self.repository.sessions, self.settings)
        if self.automations is None:
            self.automations = AutomationRepository(self.repository.sessions, self.settings, self.agent)
        if self.memory is None:
            self.memory = MemoryRepository(self.repository.sessions, self.settings)
        if self.context is None:
            self.context = ContextService(
                self.repository.sessions,
                self.settings,
                self.storage,
                self.memory,
            )
        if self.recipients is None:
            self.recipients = RecipientRepository(self.repository.sessions, self.settings)
        if self.retention is None:
            self.retention = RetentionService(self.repository.sessions, self.storage)

    @classmethod
    def create(cls, settings: Settings):
        settings.validate()
        return cls(settings, Repository(session_factory(settings.database_url), settings),
                   make_storage(settings), JwtVerifier(settings.auth_issuer, settings.auth_audience))
