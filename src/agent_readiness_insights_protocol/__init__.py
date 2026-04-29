"""Public surface of the agent-readiness insights protocol package.

Re-exports version constants, dataclasses, and serialization helpers so
consumers do `from agent_readiness_insights_protocol import Rule, ...`.
"""

from __future__ import annotations

from .models import (
    CommandInMakefileMatch,
    CompositeMatch,
    EvaluateRequest,
    EvaluateResponse,
    FileSizeMatch,
    Finding,
    HealthResponse,
    Insight,
    ManifestFieldMatch,
    Match,
    MatchType,
    PathGlobMatch,
    Pillar,
    PrivateMatch,
    RegexInFilesMatch,
    Rule,
    SearchHit,
    SearchRequest,
    SearchResponse,
    Severity,
)
from .serialization import from_json, to_json
from .version import PROTOCOL_VERSION, RULES_VERSION

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "PROTOCOL_VERSION",
    "RULES_VERSION",
    "Pillar",
    "Severity",
    "MatchType",
    "FileSizeMatch",
    "PathGlobMatch",
    "ManifestFieldMatch",
    "RegexInFilesMatch",
    "CommandInMakefileMatch",
    "CompositeMatch",
    "PrivateMatch",
    "Match",
    "Rule",
    "Insight",
    "Finding",
    "SearchHit",
    "SearchRequest",
    "SearchResponse",
    "EvaluateRequest",
    "EvaluateResponse",
    "HealthResponse",
    "to_json",
    "from_json",
]
