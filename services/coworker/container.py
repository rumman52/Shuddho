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
from .connector_reads import ConnectorReadRepository, ConnectorReadService
from .connector_push import GooglePushVerifier
from .google_actions import GoogleActions
from .microsoft_actions import MicrosoftActions
from .linkedin_actions import LinkedInActions
from .opentable_actions import OpenTableActions
from .restaurant_reservations import RestaurantReservationService
from .agent_repository import AgentRepository
from .goal_repository import GoalRepository
from .suggestion_repository import SuggestionRepository
from .suggestion_relevance_model import SuggestionRelevanceModel
from .suggestion_relevance_service import SuggestionRelevanceService
from .negotiation_repository import NegotiationRepository
from .transaction_repository import TransactionRepository
from .negotiation_model import NegotiationProposalModel
from .negotiation_service import NegotiationProposalService
from .automation_repository import AutomationRepository
from .notification_repository import NotificationRepository
from .memory_repository import MemoryRepository
from .context import ContextService
from .recipient_repository import RecipientRepository
from .retention import RetentionService
from .browser import BrowserRepository
from .sandbox import SandboxRepository


@dataclass
class Container:
    settings: Settings
    repository: Repository
    storage: object
    verifier: JwtVerifier
    actions: ActionService | None = None
    permissions: PermissionGateway | None = None
    credentials: CredentialBroker | None = None
    connector_reads: ConnectorReadService | None = None
    agent: AgentRepository | None = None
    goals: GoalRepository | None = None
    suggestions: SuggestionRepository | None = None
    suggestion_relevance: SuggestionRelevanceService | None = None
    negotiations: NegotiationRepository | None = None
    transactions: TransactionRepository | None = None
    restaurant_reservations: RestaurantReservationService | None = None
    negotiation_proposals: NegotiationProposalService | None = None
    automations: AutomationRepository | None = None
    notifications: NotificationRepository | None = None
    memory: MemoryRepository | None = None
    context: ContextService | None = None
    recipients: RecipientRepository | None = None
    retention: RetentionService | None = None
    browser: BrowserRepository | None = None
    sandbox: SandboxRepository | None = None

    def __post_init__(self):
        if self.actions is None:
            providers = {"google": GoogleActions(self.settings)}
            if self.settings.microsoft_actions_enabled:
                providers["microsoft"] = MicrosoftActions(self.settings)
            if self.settings.action_social_publishing_enabled:
                providers["linkedin"] = LinkedInActions(self.settings)
            if self.settings.restaurant_reservations_enabled:
                providers["opentable"] = OpenTableActions(self.settings)
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
        if self.connector_reads is None:
            read_repository = ConnectorReadRepository(
                self.repository.sessions,
                self.settings,
                self.permissions,
            )
            self.connector_reads = ConnectorReadService(
                read_repository,
                self.credentials,
                GooglePushVerifier(self.settings),
            )
        if self.agent is None:
            self.agent = AgentRepository(self.repository.sessions, self.settings)
        if self.goals is None:
            self.goals = GoalRepository(self.repository.sessions, self.settings)
        if self.notifications is None:
            self.notifications = NotificationRepository(
                self.repository.sessions,
                self.settings,
            )
        if self.suggestions is None:
            self.suggestions = SuggestionRepository(
                self.repository.sessions,
                self.settings,
                self.notifications,
            )
        if self.suggestion_relevance is None:
            self.suggestion_relevance = SuggestionRelevanceService(
                self.suggestions,
                SuggestionRelevanceModel(self.settings),
            )
        self.notifications.register_source_validator(
            self.suggestions.SOURCE_KIND,
            self.suggestions.notification_source_allowed,
        )
        self.notifications.register_source_validator(
            self.suggestions.EVENT_SOURCE_KIND,
            self.suggestions.event_notification_source_allowed,
        )
        if self.automations is None:
            self.automations = AutomationRepository(
                self.repository.sessions,
                self.settings,
                self.agent,
                self.notifications,
            )
        self.notifications.register_source_validator(
            self.automations.REMINDER_SOURCE_KIND,
            self.automations.reminder_notification_source_allowed,
        )
        if hasattr(self.connector_reads, "set_automation_consumer"):
            self.connector_reads.set_automation_consumer(
                self.automations.handle_connector_event
            )
        if hasattr(self.connector_reads, "set_event_consumer"):
            self.connector_reads.set_event_consumer(
                self.suggestions.handle_connector_event
            )
        if self.negotiations is None:
            self.negotiations = NegotiationRepository(
                self.repository.sessions,
                self.settings,
            )
        if self.transactions is None:
            self.transactions = TransactionRepository(
                self.repository.sessions,
                self.settings,
            )
        if self.restaurant_reservations is None:
            restaurant_adapter = self.actions.providers.get("opentable")
            if restaurant_adapter is None:
                restaurant_adapter = OpenTableActions(self.settings)
            self.restaurant_reservations = RestaurantReservationService(
                self.transactions,
                self.actions.repo,
                restaurant_adapter,
            )
        if self.negotiation_proposals is None:
            self.negotiation_proposals = NegotiationProposalService(
                self.negotiations,
                NegotiationProposalModel(self.settings),
                self.actions.repo,
            )
        if self.memory is None:
            self.memory = MemoryRepository(self.repository.sessions, self.settings)
        if self.context is None:
            self.context = ContextService(
                self.repository.sessions,
                self.settings,
                self.storage,
                self.memory,
                self.connector_reads,
            )
        if self.recipients is None:
            self.recipients = RecipientRepository(self.repository.sessions, self.settings)
        if self.browser is None:
            self.browser = BrowserRepository(self.repository.sessions, self.settings)
        if self.sandbox is None:
            self.sandbox = SandboxRepository(
                self.repository.sessions,
                self.settings,
                self.storage,
            )
        if self.retention is None:
            self.retention = RetentionService(self.repository.sessions, self.storage)

    @classmethod
    def create(cls, settings: Settings):
        settings.validate()
        return cls(settings, Repository(session_factory(settings.database_url), settings),
                   make_storage(settings), JwtVerifier(settings.auth_issuer, settings.auth_audience))
