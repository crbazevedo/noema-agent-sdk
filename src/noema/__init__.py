"""Noema Agent SDK.

Async, event-sourced, situation-aware primitives for autonomous agent systems.
"""

from .agent import AgentStatus, AutonomousAgent, AutonomousAgentConfig
from .attention import AttentionAccount, AttentionAllocator, AttentionWeights, WorkItem
from .authority import (
    ActionIntent,
    AuthorityLevel,
    AuthorizationDecision,
    AutonomyProfile,
    PolicyEngine,
    RiskLevel,
    TrustEstimate,
    TrustLedger,
)
from .capabilities import (
    Capability,
    CapabilityContext,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    FunctionCapability,
)
from .detectors import DeadlineRiskDetector, DetectorEngine, SituationDetector
from .events import AsyncEventBus, Event
from .kernel import NoemaKernel
from .reasoning import (
    ActionOutcome,
    CapabilityExistenceCritic,
    CognitiveController,
    CognitiveMode,
    CompositeReasoner,
    Critic,
    Critique,
    DecisionTrace,
    DeliberationRequest,
    DeliberationResult,
    FalsificationCritic,
    Hypothesis,
    OpportunityCostCritic,
    Reasoner,
    RuleBasedReasoner,
)
from .scheduler import AsyncScheduler, ScheduleHandle
from .situation import (
    Commitment,
    CommitmentStatus,
    Entity,
    Fact,
    Goal,
    GoalStatus,
    Opportunity,
    Relation,
    Risk,
    SituationModel,
    SituationSnapshot,
)
from .store import EventStore, InMemoryEventStore, SQLiteEventStore, copy_events
from .system import NoemaSystem
from .telemetry import InMemoryTelemetry, JsonlTelemetry, Metric, TelemetrySink

__all__ = [
    "ActionIntent",
    "ActionOutcome",
    "AgentStatus",
    "AsyncEventBus",
    "AsyncScheduler",
    "AttentionAccount",
    "AttentionAllocator",
    "AttentionWeights",
    "AuthorityLevel",
    "AuthorizationDecision",
    "AutonomousAgent",
    "AutonomousAgentConfig",
    "AutonomyProfile",
    "Capability",
    "CapabilityContext",
    "CapabilityExistenceCritic",
    "CapabilityRegistry",
    "CapabilityResult",
    "CapabilitySpec",
    "CognitiveController",
    "CognitiveMode",
    "Commitment",
    "CommitmentStatus",
    "CompositeReasoner",
    "Critic",
    "Critique",
    "DeadlineRiskDetector",
    "DecisionTrace",
    "DeliberationRequest",
    "DeliberationResult",
    "DetectorEngine",
    "Entity",
    "Event",
    "EventStore",
    "Fact",
    "FalsificationCritic",
    "FunctionCapability",
    "Goal",
    "GoalStatus",
    "Hypothesis",
    "InMemoryEventStore",
    "InMemoryTelemetry",
    "JsonlTelemetry",
    "Metric",
    "NoemaKernel",
    "NoemaSystem",
    "Opportunity",
    "OpportunityCostCritic",
    "PolicyEngine",
    "Reasoner",
    "Relation",
    "Risk",
    "RiskLevel",
    "RuleBasedReasoner",
    "SQLiteEventStore",
    "ScheduleHandle",
    "SituationDetector",
    "SituationModel",
    "SituationSnapshot",
    "TelemetrySink",
    "TrustEstimate",
    "TrustLedger",
    "WorkItem",
    "copy_events",
]

__version__ = "0.1.0"
