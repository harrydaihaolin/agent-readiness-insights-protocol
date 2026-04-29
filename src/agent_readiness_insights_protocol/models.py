"""Pydantic dataclasses shared across the insights ecosystem.

Every model uses `extra="forbid"` so unknown fields are rejected at
deserialisation. That keeps consumers honest about the contract — if
you want to add a field, add it here first.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .version import PROTOCOL_VERSION, RULES_VERSION

# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class Pillar(str, Enum):
    """Mirrors agent_readiness.models.Pillar so the schema stays in sync."""

    COGNITIVE_LOAD = "cognitive_load"
    FEEDBACK = "feedback"
    FLOW = "flow"
    SAFETY = "safety"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class MatchType(str, Enum):
    """OSS match types. Engines may add private match types
    (e.g., ast_query, churn_signal) that are NOT in this enum and that
    the OSS reference evaluator will skip with a `not_measured` finding.

    `composite` wraps any number of OSS match clauses with a boolean op
    so callers can express "A AND NOT B"-style rules without growing
    the leaf-matcher count.
    """

    FILE_SIZE = "file_size"
    PATH_GLOB = "path_glob"
    MANIFEST_FIELD = "manifest_field"
    REGEX_IN_FILES = "regex_in_files"
    COMMAND_IN_MAKEFILE = "command_in_makefile"
    COMPOSITE = "composite"


# ---------------------------------------------------------------------------
# Rule schema (RULES_VERSION = 1)
# ---------------------------------------------------------------------------


class FileSizeMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[MatchType.FILE_SIZE] = MatchType.FILE_SIZE
    threshold_lines: int = Field(default=500, ge=1)
    threshold_bytes: int = Field(default=51_200, ge=1)
    exclude_globs: list[str] = Field(default_factory=list)


class PathGlobMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[MatchType.PATH_GLOB] = MatchType.PATH_GLOB
    require_globs: list[str] = Field(default_factory=list)
    forbid_globs: list[str] = Field(default_factory=list)


class ManifestFieldMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[MatchType.MANIFEST_FIELD] = MatchType.MANIFEST_FIELD
    manifest: str = Field(description="Manifest filename, e.g. 'pyproject.toml' or 'package.json'.")
    field_path: str = Field(description="Dotted path to a required field, e.g. 'project.scripts'.")
    fire_when: Literal["missing", "present"] = "missing"


class RegexInFilesMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[MatchType.REGEX_IN_FILES] = MatchType.REGEX_IN_FILES
    pattern: str = Field(description="Python re-style regex.")
    file_globs: list[str] = Field(default_factory=lambda: ["**/*"])
    fire_when: Literal["match", "no_match"] = "match"
    case_insensitive: bool = False


class CommandInMakefileMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[MatchType.COMMAND_IN_MAKEFILE] = MatchType.COMMAND_IN_MAKEFILE
    target: str = Field(description="Makefile target name, e.g. 'test'.")
    fire_when: Literal["missing", "present"] = "missing"


class CompositeMatch(BaseModel):
    """Boolean composition over OSS leaf match clauses.

    Semantics:
    - ``and``: composite fires when every clause produces ≥1 finding.
      Emits one composite finding summarising the conjunction.
    - ``or``: composite fires when any clause produces ≥1 finding.
      Emits one finding per clause that fired (preserves details).
    - ``not``: composite fires when the (single) clause produces 0
      findings. Used to express "X is missing".

    Nested ``CompositeMatch`` clauses are allowed up to a small depth
    (engines should cap recursion at 4 to keep evaluation predictable).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal[MatchType.COMPOSITE] = MatchType.COMPOSITE
    op: Literal["and", "or", "not"]
    clauses: list[
        "FileSizeMatch | PathGlobMatch | ManifestFieldMatch | "
        "RegexInFilesMatch | CommandInMakefileMatch | CompositeMatch"
    ] = Field(default_factory=list, min_length=1)
    summary: str | None = Field(
        default=None,
        description="Optional human-readable summary used as the composite finding message.",
    )


Match = Annotated[
    FileSizeMatch
    | PathGlobMatch
    | ManifestFieldMatch
    | RegexInFilesMatch
    | CommandInMakefileMatch
    | CompositeMatch,
    Field(discriminator="type"),
]


CompositeMatch.model_rebuild()


class Rule(BaseModel):
    """Declarative rule. Loaded from YAML; produced as JSON by `/rules`.

    `rules_version` is the schema version of THIS rule file; loaders
    refuse rules whose rules_version is outside their supported range.
    """

    model_config = ConfigDict(extra="forbid")

    rules_version: int = Field(
        default=RULES_VERSION,
        description="Schema version this rule conforms to. Loaders gate on this.",
    )
    id: str = Field(description="Stable identifier, e.g. 'repo_shape.large_files'.")
    pillar: Pillar
    title: str
    weight: float = Field(default=1.0, ge=0.0, le=10.0)
    severity: Severity = Severity.WARN
    explanation: str = Field(default="", description="Why this rule predicts an agent failure mode.")
    match: Match
    fix_hint: str | None = None
    insight_query: str | None = Field(
        default=None,
        description="Free-text query the engine uses to retrieve related insights for findings of this rule.",
    )


# ---------------------------------------------------------------------------
# Findings (per-finding, produced by the evaluator)
# ---------------------------------------------------------------------------


class Insight(BaseModel):
    """A retrieved insight chunk attached to a finding by the engine."""

    model_config = ConfigDict(extra="forbid")

    text: str
    source: str = Field(description="Origin label, e.g. 'research/ideas.md' or 'leaderboard/scores.json'.")
    score: float = Field(ge=0.0, le=1.0, description="Relevance score from the vector store.")
    metadata: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    pillar: Pillar
    severity: Severity
    message: str
    file: str | None = None
    line: int | None = None
    fix_hint: str | None = None
    related_insights: list[Insight] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RAG search
# ---------------------------------------------------------------------------


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source: str
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str
    k: int = Field(default=5, ge=1, le=50)
    pillar: Pillar | None = None
    rule_id: str | None = None


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: int = Field(default=PROTOCOL_VERSION)
    hits: list[SearchHit] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_path: str
    with_insights: bool = True
    rule_ids: list[str] | None = Field(
        default=None,
        description="If set, evaluate only these rule ids; otherwise evaluate the full pack.",
    )


class EvaluateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: int = Field(default=PROTOCOL_VERSION)
    findings: list[Finding] = Field(default_factory=list)
    repo_path: str
    rules_evaluated: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Returned by GET /healthz on any insights engine.

    Clients use `protocol_version` to gate calls. `rules_version_supported`
    is informational; the engine handles rule loading internally.
    """

    model_config = ConfigDict(extra="forbid")

    protocol_version: int = Field(default=PROTOCOL_VERSION)
    rules_version_supported: list[int] = Field(default_factory=lambda: [RULES_VERSION])
    rules_pack_version_loaded: str | None = None
    private_rules_count: int = Field(default=0, ge=0)
    engine_version: str
    status: Literal["ok", "degraded"] = "ok"


__all__ = [
    "Pillar",
    "Severity",
    "MatchType",
    "FileSizeMatch",
    "PathGlobMatch",
    "ManifestFieldMatch",
    "RegexInFilesMatch",
    "CommandInMakefileMatch",
    "CompositeMatch",
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
]
