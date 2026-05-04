"""Pydantic dataclasses shared across the insights ecosystem.

Every model uses `extra="forbid"` so unknown fields are rejected at
deserialisation. That keeps consumers honest about the contract — if
you want to add a field, add it here first.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .version import PROTOCOL_VERSION, RULES_VERSION, RULES_VERSION_MIN_SUPPORTED

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

    Each leaf clause is "satisfied" when its matcher returns no
    findings (the required paths exist, the required regex matches,
    the manifest field is set, …). Composite ops are defined over
    that per-clause satisfied / unsatisfied bit:

    - ``and``: composite is satisfied iff every clause is satisfied.
      When any clause is unsatisfied, emits one composite finding
      summarising which conjunct(s) failed (callers typically use
      ``summary`` to carry the human-readable conjunction text).
    - ``or``: composite is satisfied iff at least one clause is
      satisfied. When ALL clauses are unsatisfied, emits one finding
      per failing clause so the user sees each unmet alternative,
      prefixed by ``summary`` (if set) so the reporter can label the
      all-fail case explicitly.
    - ``not``: composite is satisfied iff the (single) clause is
      unsatisfied. Used to express "X is missing"; emits one finding
      naming what ``X`` was when the inner clause was satisfied.

    Note on ``or``: an earlier revision of this docstring described
    ``or`` as "fires when any clause produces ≥1 finding" (i.e.
    OR-of-failures). That wording was inverted relative to how every
    rule in the agent-readiness rules pack uses ``or``  — "any of
    these alternatives is acceptable" — and was producing 6+
    spurious findings per scanned repo. The semantic above
    (OR-of-satisfactions) is the corrected, canonical contract.

    Nested ``CompositeMatch`` clauses are allowed up to a small depth
    (engines should cap recursion at 4 to keep evaluation predictable).
    ``PrivateMatch`` clauses are also accepted so composite expressions
    can incorporate downstream-engine analyses.
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


# ---------------------------------------------------------------------------
# Action contract (RULES_VERSION = 2)
# ---------------------------------------------------------------------------
#
# Every rule whose ``rules_version >= 2`` must emit a structured
# ``action`` object plus a ``verify`` step. The contract turns each
# finding into a deterministic concrete instruction an autonomous coding
# agent can execute and verify without reading any other file.
#
# ``Action`` is a discriminated union over six action kinds. The first
# three (``create_file``, ``append_to_file``, ``insert_after``) mirror
# the legacy ``FixTemplate`` shapes but carry optional ``preconditions``
# and ``context_probe`` blocks so the engine can gate evaluation and
# render ``{variable}`` substitutions at scan time. The new three
# (``edit_gitignore``, ``modify_manifest_field``, ``run_command``) cover
# the actions that ``FixTemplate`` could not express.


class ContextProbeKind(str, Enum):
    """Probes the engine runs at scan time to populate ``{variable}``s
    inside an ``action.template``. Each kind is deterministic — no LLM
    in the action path."""

    PRIMARY_LANGUAGE = "primary_language"
    PRIMARY_MANIFEST = "primary_manifest"
    PACKAGE_MANAGER = "package_manager"
    MAKEFILE_TARGETS = "makefile_targets"
    EXISTING_ENTRY_POINTS = "existing_entry_points"
    TEST_DIRECTORY = "test_directory"
    CI_PRESENT = "ci_present"
    LOCKFILE_PRESENT = "lockfile_present"


class ContextProbe(BaseModel):
    """A single probe declared on an action.

    ``detect`` names the signal to capture from the repo; the engine
    binds the result to ``{<detect>}`` placeholders inside
    ``action.template``. Probes that the engine cannot resolve emit
    an empty string so templates degrade gracefully.
    """

    model_config = ConfigDict(extra="forbid")

    detect: ContextProbeKind


class Precondition(BaseModel):
    """A simple structural precondition the engine evaluates before
    emitting the action.

    All non-null fields must hold for the action to fire. Omit fields
    that are not relevant. Used by ``rules_pack >= 2`` to keep actions
    targeted (e.g. don't suggest editing a Makefile when none exists).
    """

    model_config = ConfigDict(extra="forbid")

    exists: str | None = Field(
        default=None,
        description="Repo-relative path that must exist for this action to fire.",
    )
    not_exists: str | None = Field(
        default=None,
        description="Repo-relative path that must NOT exist for this action to fire.",
    )
    manifest_language: str | None = Field(
        default=None,
        description="Required primary language (e.g. 'python', 'node', 'go').",
    )
    has_makefile_target: str | None = Field(
        default=None,
        description="Required existing Makefile target name.",
    )


class _ActionBase(BaseModel):
    """Common fields shared by every action kind."""

    model_config = ConfigDict(extra="forbid")

    preconditions: list[Precondition] = Field(default_factory=list)
    context_probe: list[ContextProbe] = Field(default_factory=list)


class CreateFileAction(_ActionBase):
    """Materialise a brand-new file with the given content / template."""

    kind: Literal["create_file"] = "create_file"
    path: str = Field(description="Repo-relative path of the new file.")
    template: str = Field(
        description=(
            "Full file contents to create. May contain ``{variable}`` "
            "placeholders populated by ``context_probe`` at scan time."
        ),
    )


class AppendToFileAction(_ActionBase):
    """Append content to an existing file (or create if absent)."""

    kind: Literal["append_to_file"] = "append_to_file"
    path: str
    template: str


class InsertAfterAction(_ActionBase):
    """Insert content immediately after the first line matching ``after_pattern``."""

    kind: Literal["insert_after"] = "insert_after"
    path: str
    after_pattern: str = Field(
        description="Python re-style regex matched against the file with re.MULTILINE.",
    )
    template: str


class EditGitignoreAction(_ActionBase):
    """Append entries to ``.gitignore`` (creating it if absent)."""

    kind: Literal["edit_gitignore"] = "edit_gitignore"
    entries: list[str] = Field(
        default_factory=list, min_length=1,
        description="Glob patterns to append, one per line.",
    )


class ModifyManifestFieldAction(_ActionBase):
    """Set / merge a field inside a structured manifest (TOML/JSON/YAML).

    ``value`` is a string the engine inserts under ``field_path``. For
    JSON / YAML the engine parses-edit-rewrites; for TOML it appends a
    fresh table if the field is missing.
    """

    kind: Literal["modify_manifest_field"] = "modify_manifest_field"
    manifest: str = Field(description="Manifest filename, e.g. 'pyproject.toml'.")
    field_path: str = Field(description="Dotted path to the target field.")
    value: str = Field(description="Literal value to set (string-encoded).")


class RunCommandAction(_ActionBase):
    """Run a shell command in the repo root.

    Used for actions that aren't a single file edit (initialising a
    devcontainer, scaffolding a CI workflow with `gh extension`, etc.).
    The command MUST be deterministic and offline-safe; agents may
    refuse to execute network calls.
    """

    kind: Literal["run_command"] = "run_command"
    command: str = Field(description="Shell command to run from the repo root.")
    description: str = Field(default="")


Action = (
    CreateFileAction
    | AppendToFileAction
    | InsertAfterAction
    | EditGitignoreAction
    | ModifyManifestFieldAction
    | RunCommandAction
)


class VerifyStep(BaseModel):
    """The verification command an agent runs after applying an action.

    Must exit 0 when the rule would no longer fire on the modified
    repo. Should be deterministic, offline (network is forbidden), and
    fast (≤ ``timeout_seconds``).
    """

    model_config = ConfigDict(extra="forbid")

    command: str = Field(
        description="Shell command; exit 0 = fix landed, non-zero = still missing.",
    )
    description: str = Field(default="")
    timeout_seconds: int = Field(default=15, ge=1, le=300)
    offline: bool = Field(default=True)


class Rule(BaseModel):
    """Declarative rule. Loaded from YAML; produced as JSON by `/rules`.

    `rules_version` is the schema version of THIS rule file; loaders
    refuse rules whose rules_version is outside their supported range.

    For ``rules_version >= 2`` the rule MUST carry an ``action`` block
    and a ``verify`` step (the deterministic action contract). Older
    v1 rules are still accepted during the transition window; their
    legacy ``fix_template`` field is automatically mapped to ``action``
    by the engine when emitting findings.
    """

    model_config = ConfigDict(extra="forbid")

    rules_version: int = Field(
        default=RULES_VERSION_MIN_SUPPORTED,
        description=(
            "Schema version this rule conforms to. Defaults to the lowest "
            "supported version so legacy YAMLs without an explicit "
            "``rules_version:`` line still validate. New rules should "
            "set this to RULES_VERSION (the latest) and supply an "
            "``action`` + ``verify`` pair. Loaders gate on this."
        ),
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
            "Deprecated as of rules_version 2 — use ``action`` instead. "
            "Retained for backward compatibility; engines auto-map it onto "
            "the matching ``Action`` model when surfacing findings."
        ),
    )
    action: Action | None = Field(
        default=None,
        description=(
            "Structured deterministic action — the agent's instruction "
            "for what to change, where, and how. Required for "
            "``rules_version >= 2``. Carries optional ``preconditions`` "
            "and ``context_probe`` blocks so the engine can gate emission "
            "and substitute repo signals into ``{variable}`` placeholders."
        ),
    )
    verify: VerifyStep | None = Field(
        default=None,
        description=(
            "Verification step the agent runs after applying ``action`` "
            "to confirm the fix landed. Required for ``rules_version >= 2``."
        ),
    )
    insight_query: str | None = Field(
        default=None,
        description="Free-text query the engine uses to retrieve related insights for findings of this rule.",
    )
    provenance: str = Field(
        description=(
            "Attribution string identifying the upstream origin of this "
            "rule. Required so every rule that ships with this protocol "
            "carries a clear authorship trail. Format: "
            "``agent-readiness/<rule-id>`` for native rules, "
            "``<owner>/<repo>#<anchor>`` for ports of other open-source "
            "rule packs (e.g. ``microsoft/agentrc#docs.agents-md``). The "
            "field is mandatory; contributors who fork this protocol must "
            "preserve the provenance line of any rule they redistribute."
        ),
    )

    @model_validator(mode="after")
    def _v2_requires_action_and_verify(self) -> Rule:
        """``rules_version >= 2`` must carry both ``action`` and ``verify``.

        v1 rules are accepted as-is so the transition window doesn't
        block downstream consumers. Engines may auto-derive an
        ``action`` from ``fix_template`` for v1 rules at finding-emit
        time.
        """
        if self.rules_version >= 2:
            if self.action is None:
                raise ValueError(
                    f"rule {self.id!r}: rules_version={self.rules_version} requires "
                    "a non-null `action` block (deterministic action contract)."
                )
            if self.verify is None:
                raise ValueError(
                    f"rule {self.id!r}: rules_version={self.rules_version} requires "
                    "a non-null `verify` block (closed-loop fix verification)."
                )
        return self


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
    action: Action | None = Field(
        default=None,
        description=(
            "Concrete, deterministic action the agent should take. For "
            "rules_version >= 2 this mirrors the rule's `action` field "
            "(with `{variable}` placeholders resolved from `context_probe`). "
            "For v1 rules, engines may auto-map `fix_template` onto an "
            "Action so consumers see one shape regardless of source."
        ),
    )
    verify: VerifyStep | None = Field(
        default=None,
        description=(
            "Verification step the agent runs after applying `action`. "
            "Required for rules_version >= 2 findings; absent on v1 "
            "fix_template-only findings."
        ),
    )
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
    "ContextProbeKind",
    "ContextProbe",
    "Precondition",
    "CreateFileAction",
    "AppendToFileAction",
    "InsertAfterAction",
    "EditGitignoreAction",
    "ModifyManifestFieldAction",
    "RunCommandAction",
    "Action",
    "VerifyStep",
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
