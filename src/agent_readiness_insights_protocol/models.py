"""Pydantic dataclasses shared across the insights ecosystem.

Every model uses `extra="forbid"` so unknown fields are rejected at
deserialisation. That keeps consumers honest about the contract — if
you want to add a field, add it here first.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .version import PROTOCOL_VERSION, RULES_VERSION

# Frozen at module import: every match type the OSS reference evaluator
# recognises. ``PrivateMatch.type`` is forbidden from taking any of these
# values so a malformed ``file_size`` rule cannot silently fall through to
# the catch-all PrivateMatch branch.
_OSS_MATCH_TYPES: frozenset[str] = frozenset({
    "file_size",
    "path_glob",
    "manifest_field",
    "regex_in_files",
    "command_in_makefile",
    "composite",
})

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
    PrivateMatch clauses are also accepted so composite expressions can
    incorporate downstream-engine analyses.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal[MatchType.COMPOSITE] = MatchType.COMPOSITE
    op: Literal["and", "or", "not"]
    clauses: list[
        "FileSizeMatch | PathGlobMatch | ManifestFieldMatch | "
        "RegexInFilesMatch | CommandInMakefileMatch | CompositeMatch | "
        "PrivateMatch"
    ] = Field(default_factory=list, min_length=1)
    summary: str | None = Field(
        default=None,
        description="Optional human-readable summary used as the composite finding message.",
    )


class PrivateMatch(BaseModel):
    """Catch-all for non-OSS (private) match types.

    Downstream engines (e.g. ``agent-readiness-pro`` or the closed
    insights engine) extend the rules pack with bespoke analyses such as
    ``git_log_query``, ``ast_complexity``, or ``regex_secret_scan``.
    These are registered in the engine via
    ``register_private_matcher(type_name, fn)`` and are referenced from
    YAML rules as ``match.type: <name>``.

    The protocol does not specify the *shape* of a PrivateMatch — every
    field beyond ``type`` is engine-specific — so this model accepts
    arbitrary extra fields. ``type`` is constrained only to forbid the
    six OSS match-type names, preventing a malformed OSS rule from
    silently being parsed as a private one. Engines that do not know
    a given private type produce a ``not_measured`` finding rather
    than crashing.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(description="Engine-specific match type name; must NOT collide with an OSS type.")

    @field_validator("type")
    @classmethod
    def _not_oss_type(cls, v: str) -> str:
        if v in _OSS_MATCH_TYPES:
            raise ValueError(
                f"{v!r} is a built-in OSS match type; private match types "
                "must use a distinct name. If you intended to use the OSS "
                "type, fix the rule's structural fields instead of routing "
                "through PrivateMatch."
            )
        return v


# Plain Union (no Field(discriminator=...) annotation) so pydantic 2's
# "smart" union mode can route OSS-typed dicts to the typed variants and
# fall through to PrivateMatch only for unknown ``type`` values.
# PrivateMatch *must* be last so the typed variants are tried first.
Match = (
    FileSizeMatch
    | PathGlobMatch
    | ManifestFieldMatch
    | RegexInFilesMatch
    | CommandInMakefileMatch
    | CompositeMatch
    | PrivateMatch
)


CompositeMatch.model_rebuild()


class CreateFileFix(BaseModel):
    """Materialise a brand-new file with the given contents.

    Diffed against an empty buffer so dashboards render the whole file
    as an added hunk.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["create_file"] = "create_file"
    path: str = Field(description="Repo-relative path of the new file.")
    content: str = Field(description="Full file contents to create.")


class AppendToFileFix(BaseModel):
    """Append content to an existing file (or create if absent)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["append_to_file"] = "append_to_file"
    path: str
    content: str


class InsertAfterFix(BaseModel):
    """Insert content immediately after the first line matching ``after_pattern``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["insert_after"] = "insert_after"
    path: str
    after_pattern: str = Field(
        description="Python re-style regex matched against the file with re.MULTILINE."
    )
    content: str


# Discriminated union; pydantic v2 routes by ``kind``.
FixTemplate = CreateFileFix | AppendToFileFix | InsertAfterFix


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
    fix_template: FixTemplate | None = Field(
        default=None,
        description=(
            "Optional deterministic fix recipe. The engine renders this "
            "into a unified diff at scan time and attaches it to each "
            "finding so dashboards can offer a one-click suggested patch."
        ),
    )
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
    snippet: str | None = Field(
        default=None,
        description=(
            "Short excerpt of the offending source (typically the matched line "
            "with a couple of lines of context). Always plain text, never HTML."
        ),
    )
    suggested_patch: str | None = Field(
        default=None,
        description=(
            "Unified-diff hunk representing a suggested fix. Optional; only "
            "rules with a deterministic fix template emit this. Consumers may "
            "render this as a code review-style diff."
        ),
    )


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
    "PrivateMatch",
    "Match",
    "CreateFileFix",
    "AppendToFileFix",
    "InsertAfterFix",
    "FixTemplate",
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
