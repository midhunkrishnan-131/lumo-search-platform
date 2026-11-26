"""Database models package."""

from app.models.crawler import CrawlSession, CrawlUrl
from app.models.document import Document
from app.models.history import BrowsingHistory, SearchHistory
from app.models.research import ResearchSession
from app.models.guardian import GuardianAnalysis
from app.models.graph import (
    Entity,
    EntityAlias,
    EntityDocument,
    EntityResolutionLog,
    Relationship,
    RelationshipEvidence,
)
from app.models.workspace import (
    WorkspaceAnnotation,
    WorkspaceCollection,
    WorkspaceItem,
    WorkspaceItemTag,
    WorkspaceNote,
    WorkspaceNoteTag,
    WorkspaceTag,
)
from app.models.automation import (
    Automation,
    AutomationExecution,
    AutomationExecutionStep,
    AutomationNotification,
)
from app.models.personalization import (
    PersonalizationFeedback,
    PersonalizationSettings,
    SourcePreference,
    TopicProfile,
    UserInterest,
)
from app.models.intelligence import (
    UniversalAnalysisReport,
    UniversalDataset,
    UniversalImportJob,
)
from app.models.integrations import (
    IntegrationImportRecord,
    IntegrationRecord,
    IntegrationSource,
    IntegrationSyncRun,
)
from app.models.developer import ApiKey, ApiUsageLog
from app.models.evaluation import (
    EvaluationBenchmark,
    EvaluationDataset,
    EvaluationReview,
    EvaluationRun,
)
from app.models.workflow import IntelligenceWorkflow, IntelligenceWorkflowStep
from app.models.knowledge_hub import (
    KnowledgeActivity,
    KnowledgeCollectionMeta,
    KnowledgeItemMeta,
    KnowledgeRelationship,
)
from app.models.retrieval import IndexedRecord
from app.models.studio import StudioProject, StudioProjectVersion

__all__ = [
    "CrawlSession",
    "CrawlUrl",
    "Document",
    "SearchHistory",
    "BrowsingHistory",
    "ResearchSession",
    "GuardianAnalysis",
    "Entity",
    "EntityAlias",
    "EntityDocument",
    "Relationship",
    "RelationshipEvidence",
    "EntityResolutionLog",
    "WorkspaceCollection",
    "WorkspaceTag",
    "WorkspaceItem",
    "WorkspaceItemTag",
    "WorkspaceNote",
    "WorkspaceNoteTag",
    "WorkspaceAnnotation",
    "Automation",
    "AutomationExecution",
    "AutomationExecutionStep",
    "AutomationNotification",
    "PersonalizationSettings",
    "UserInterest",
    "TopicProfile",
    "SourcePreference",
    "PersonalizationFeedback",
    "UniversalDataset",
    "UniversalImportJob",
    "UniversalAnalysisReport",
    "IntegrationRecord",
    "IntegrationSource",
    "IntegrationSyncRun",
    "IntegrationImportRecord",
    "ApiKey",
    "ApiUsageLog",
    "EvaluationDataset",
    "EvaluationBenchmark",
    "EvaluationRun",
    "EvaluationReview",
]
