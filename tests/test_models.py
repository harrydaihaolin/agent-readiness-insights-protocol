"""Tests for the protocol dataclasses, version constants, and serializers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_readiness_insights_protocol import (
    PROTOCOL_VERSION,
    RULES_VERSION,
    RULES_VERSION_MIN_SUPPORTED,
    AppendToFileAction,
    AppendToFileFix,
    CompositeMatch,
    ContextProbe,
    ContextProbeKind,
    CreateFileAction,
    CreateFileFix,
    EditGitignoreAction,
    EvaluateRequest,
    EvaluateResponse,
    FileSizeMatch,
    Finding,
    HealthResponse,
    InsertAfterAction,
    InsertAfterFix,
    Insight,
    ManifestFieldMatch,
    ModifyManifestFieldAction,
    PathGlobMatch,
    Pillar,
    Precondition,
    PrivateMatch,
    RegexInFilesMatch,
    Rule,
    RunCommandAction,
    SearchHit,
    SearchRequest,
    SearchResponse,
    Severity,
    VerifyStep,
    from_json,
    to_json,
)
from pydantic import ValidationError


class TestVersionConstants:
    def test_protocol_version_is_two(self):
        assert PROTOCOL_VERSION == 2

    def test_rules_version_is_two(self):
        assert RULES_VERSION == 2

    def test_rules_version_min_supported_is_one(self):
        # v1 rules must keep validating during the transition window.
        assert RULES_VERSION_MIN_SUPPORTED == 1


class TestRule:
    def test_minimal_rule_with_file_size_match(self):
        rule = Rule(
            id="repo_shape.large_files",
            pillar=Pillar.COGNITIVE_LOAD,
            title="Large files",
            match=FileSizeMatch(),
        )
        # v1 default keeps backward compatibility with un-versioned YAML.
        assert rule.rules_version == RULES_VERSION_MIN_SUPPORTED
        assert rule.weight == 1.0
        assert rule.severity == Severity.WARN
        assert rule.match.threshold_lines == 500

    def test_rule_with_manifest_field_match(self):
        rule = Rule(
            id="manifest.has_scripts",
            pillar=Pillar.COGNITIVE_LOAD,
            title="Manifest declares scripts",
            match=ManifestFieldMatch(manifest="pyproject.toml", field_path="project.scripts"),
        )
        assert rule.match.manifest == "pyproject.toml"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            Rule(
                id="x",
                pillar=Pillar.FLOW,
                title="x",
                match=FileSizeMatch(),
                unknown_field="should fail",
            )

    def test_serialization_roundtrip(self):
        rule = Rule(
            id="repo_shape.large_files",
            pillar=Pillar.COGNITIVE_LOAD,
            title="Large files",
            match=FileSizeMatch(threshold_lines=300, exclude_globs=["*.lock"]),
            insight_query="large files",
        )
        s = to_json(rule)
        restored = from_json(Rule, s)
        assert restored == rule

    def test_match_discriminated_union(self):
        # YAML-style dict with `type` key chooses the right variant
        rule = Rule.model_validate(
            {
                "id": "scripts.file_size",
                "pillar": "cognitive_load",
                "title": "file size",
                "match": {"type": "file_size", "threshold_lines": 200},
            }
        )
        assert isinstance(rule.match, FileSizeMatch)
        assert rule.match.threshold_lines == 200

    def test_composite_match_and(self):
        rule = Rule.model_validate(
            {
                "id": "env.parity_strict",
                "pillar": "flow",
                "title": "env reads but no .env.example",
                "match": {
                    "type": "composite",
                    "op": "and",
                    "summary": "env reads exist AND .env.example missing",
                    "clauses": [
                        {"type": "regex_in_files",
                         "pattern": "os\\.environ",
                         "file_globs": ["src/**/*.py"],
                         "fire_when": "match"},
                        {"type": "path_glob", "require_globs": [".env.example"]},
                    ],
                },
            }
        )
        assert isinstance(rule.match, CompositeMatch)
        assert rule.match.op == "and"
        assert len(rule.match.clauses) == 2
        assert isinstance(rule.match.clauses[0], RegexInFilesMatch)
        assert isinstance(rule.match.clauses[1], PathGlobMatch)

    def test_composite_match_not(self):
        rule = Rule.model_validate(
            {
                "id": "agent_docs.absent",
                "pillar": "cognitive_load",
                "title": "Fires when AGENTS.md present (demo)",
                "match": {
                    "type": "composite",
                    "op": "not",
                    "clauses": [
                        {"type": "path_glob", "require_globs": ["AGENTS.md"]},
                    ],
                },
            }
        )
        assert isinstance(rule.match, CompositeMatch)
        assert rule.match.op == "not"

    def test_composite_match_nested(self):
        # composite of composites should validate
        rule = Rule.model_validate(
            {
                "id": "x.nested",
                "pillar": "flow",
                "title": "nested composite",
                "match": {
                    "type": "composite",
                    "op": "or",
                    "clauses": [
                        {"type": "composite", "op": "and", "clauses": [
                            {"type": "path_glob", "require_globs": ["A"]},
                            {"type": "path_glob", "require_globs": ["B"]},
                        ]},
                        {"type": "path_glob", "require_globs": ["C"]},
                    ],
                },
            }
        )
        assert isinstance(rule.match, CompositeMatch)
        assert rule.match.op == "or"
        assert isinstance(rule.match.clauses[0], CompositeMatch)
        assert rule.match.clauses[0].op == "and"

    def test_composite_match_empty_clauses_rejected(self):
        with pytest.raises(ValidationError):
            Rule.model_validate(
                {
                    "id": "bad.composite",
                    "pillar": "flow",
                    "title": "no clauses",
                    "match": {"type": "composite", "op": "and", "clauses": []},
                }
            )


class TestPrivateMatch:
    """PrivateMatch is the catch-all for downstream-engine match types.

    The protocol does not specify the *shape* of a PrivateMatch (every
    field beyond `type` is engine-specific) so these tests focus on the
    boundary: arbitrary types pass through, OSS type names are forbidden,
    rules carrying a private match still validate end-to-end, and the
    union routes correctly between typed and private variants.
    """

    def test_minimal_private_match(self):
        m = PrivateMatch(type="git_log_query")
        assert m.type == "git_log_query"

    def test_private_match_accepts_arbitrary_extra_fields(self):
        m = PrivateMatch.model_validate(
            {
                "type": "ast_complexity",
                "languages": ["python", "typescript"],
                "max_cc": 15,
                "include_globs": ["src/**/*.py"],
            }
        )
        assert m.type == "ast_complexity"
        # extra="allow" stores unknown fields on __pydantic_extra__
        assert m.model_extra == {
            "languages": ["python", "typescript"],
            "max_cc": 15,
            "include_globs": ["src/**/*.py"],
        }

    @pytest.mark.parametrize(
        "oss_type",
        [
            "file_size",
            "path_glob",
            "manifest_field",
            "regex_in_files",
            "command_in_makefile",
            "composite",
        ],
    )
    def test_private_match_rejects_oss_type_names(self, oss_type):
        with pytest.raises(ValidationError) as exc:
            PrivateMatch(type=oss_type)
        assert "built-in OSS match type" in str(exc.value)

    def test_rule_with_private_match_validates(self):
        rule = Rule.model_validate(
            {
                "id": "git.has_history",
                "pillar": "flow",
                "title": "Repo has git history",
                "match": {
                    "type": "git_log_query",
                    "command": "rev-list --count HEAD",
                    "min_count": 5,
                },
            }
        )
        assert isinstance(rule.match, PrivateMatch)
        assert rule.match.type == "git_log_query"
        assert rule.match.model_extra["min_count"] == 5

    def test_union_routes_oss_type_to_typed_variant_not_private(self):
        # When type matches an OSS variant, pydantic should route to the
        # typed model (FileSizeMatch), not the catch-all PrivateMatch.
        rule = Rule.model_validate(
            {
                "id": "x",
                "pillar": "cognitive_load",
                "title": "x",
                "match": {"type": "file_size", "threshold_lines": 100},
            }
        )
        assert isinstance(rule.match, FileSizeMatch)
        assert not isinstance(rule.match, PrivateMatch)

    def test_malformed_oss_match_does_not_silently_fall_through(self):
        # ``type: file_size`` with bad fields must fail loudly instead of
        # being parsed as a PrivateMatch (which would silently lose the
        # OSS type's structural validation).
        with pytest.raises(ValidationError):
            Rule.model_validate(
                {
                    "id": "x",
                    "pillar": "cognitive_load",
                    "title": "x",
                    "match": {"type": "file_size", "threshold_lines": -1},
                }
            )

    def test_composite_can_contain_private_clauses(self):
        rule = Rule.model_validate(
            {
                "id": "complex.signal",
                "pillar": "safety",
                "title": "code complexity AND high churn",
                "match": {
                    "type": "composite",
                    "op": "and",
                    "summary": "complex AND churned",
                    "clauses": [
                        {
                            "type": "ast_complexity",
                            "max_cc": 15,
                            "languages": ["python"],
                        },
                        {
                            "type": "git_log_query",
                            "min_commits_touching_file": 10,
                        },
                    ],
                },
            }
        )
        assert isinstance(rule.match, CompositeMatch)
        assert len(rule.match.clauses) == 2
        assert all(isinstance(c, PrivateMatch) for c in rule.match.clauses)
        assert rule.match.clauses[0].type == "ast_complexity"
        assert rule.match.clauses[1].type == "git_log_query"

    def test_private_match_serialization_roundtrip(self):
        rule = Rule(
            id="git.has_history",
            pillar=Pillar.FLOW,
            title="Repo has git history",
            match=PrivateMatch.model_validate(
                {
                    "type": "git_log_query",
                    "command": "rev-list --count HEAD",
                    "min_count": 5,
                }
            ),
        )
        s = to_json(rule)
        restored = from_json(Rule, s)
        assert isinstance(restored.match, PrivateMatch)
        assert restored.match.type == "git_log_query"
        assert restored.match.model_extra["min_count"] == 5


class TestEvaluate:
    def test_request_minimal(self):
        req = EvaluateRequest(repo_path="/tmp/x")
        assert req.with_insights is True
        assert req.rule_ids is None

    def test_response_default_protocol_version(self):
        resp = EvaluateResponse(repo_path="/tmp/x")
        assert resp.protocol_version == PROTOCOL_VERSION
        assert resp.findings == []

    def test_response_with_finding_and_insight(self):
        finding = Finding(
            rule_id="repo_shape.large_files",
            pillar=Pillar.COGNITIVE_LOAD,
            severity=Severity.WARN,
            message="Large file: src/big.py",
            file="src/big.py",
            line=None,
            related_insights=[
                Insight(
                    text="Common false positive: lock files",
                    source="research/ideas.md",
                    score=0.87,
                )
            ],
        )
        resp = EvaluateResponse(repo_path="/x", findings=[finding], rules_evaluated=7)
        s = to_json(resp)
        restored = from_json(EvaluateResponse, s)
        assert restored.findings[0].related_insights[0].score == 0.87


class TestFixTemplate:
    """``Rule.fix_template`` is the optional deterministic-patch recipe.

    Three discriminated kinds (``create_file``, ``append_to_file``,
    ``insert_after``) cover the common deterministic fixes; the engine
    materialises them into a unified diff at scan time. These tests
    exercise the *protocol surface* only — not patch generation.
    """

    def test_rule_without_fix_template_is_valid(self):
        rule = Rule(
            id="x",
            pillar=Pillar.FLOW,
            title="x",
            match=FileSizeMatch(),
        )
        assert rule.fix_template is None

    def test_rule_with_create_file_fix_via_dict(self):
        rule = Rule.model_validate(
            {
                "id": "x",
                "pillar": "feedback",
                "title": "x",
                "match": {"type": "path_glob", "require_globs": ["AGENTS.md"]},
                "fix_template": {
                    "kind": "create_file",
                    "path": "AGENTS.md",
                    "content": "# Agent guide\n",
                },
            }
        )
        assert isinstance(rule.fix_template, CreateFileFix)
        assert rule.fix_template.path == "AGENTS.md"

    def test_rule_with_append_to_file_fix(self):
        ft = AppendToFileFix(path=".gitignore", content=".env\n")
        rule = Rule(
            id="x",
            pillar=Pillar.SAFETY,
            title="x",
            match=FileSizeMatch(),
            fix_template=ft,
        )
        s = to_json(rule)
        restored = from_json(Rule, s)
        assert isinstance(restored.fix_template, AppendToFileFix)
        assert restored.fix_template.content == ".env\n"

    def test_rule_with_insert_after_fix(self):
        ft = InsertAfterFix(
            path="Makefile",
            after_pattern=r"^all:",
            content="\ntest:\n\tpytest\n",
        )
        rule = Rule(
            id="x",
            pillar=Pillar.FEEDBACK,
            title="x",
            match=FileSizeMatch(),
            fix_template=ft,
        )
        assert isinstance(rule.fix_template, InsertAfterFix)
        assert rule.fix_template.after_pattern == r"^all:"

    def test_fix_template_unknown_kind_rejected(self):
        with pytest.raises(ValidationError):
            Rule.model_validate(
                {
                    "id": "x",
                    "pillar": "flow",
                    "title": "x",
                    "match": {"type": "path_glob", "require_globs": ["X"]},
                    "fix_template": {
                        "kind": "delete_file",  # not allowed
                        "path": "X",
                    },
                }
            )

    def test_fix_template_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            CreateFileFix(path="x", content="y", extra_field="boom")


class TestFindingCodeContext:
    """Optional snippet/suggested_patch fields surface code-level context to
    consumers (dashboards, code-review UX). These are *additive* — older
    findings without the fields must still validate.
    """

    def test_finding_without_code_context_is_valid(self):
        finding = Finding(
            rule_id="x",
            pillar=Pillar.FLOW,
            severity=Severity.WARN,
            message="generic finding",
        )
        assert finding.snippet is None
        assert finding.suggested_patch is None

    def test_finding_with_snippet_only(self):
        finding = Finding(
            rule_id="x",
            pillar=Pillar.FLOW,
            severity=Severity.WARN,
            message="line offending",
            file="src/foo.py",
            line=42,
            snippet="    bad_code()\n",
        )
        assert finding.snippet == "    bad_code()\n"
        assert finding.suggested_patch is None

    def test_finding_with_suggested_patch(self):
        diff = (
            "--- a/Makefile\n"
            "+++ b/Makefile\n"
            "@@ -1,2 +1,5 @@\n"
            " all:\n"
            "+\n"
            "+test:\n"
            "+\tpytest\n"
        )
        finding = Finding(
            rule_id="feedback.test_command",
            pillar=Pillar.FEEDBACK,
            severity=Severity.WARN,
            message="No `test` target in Makefile",
            file="Makefile",
            suggested_patch=diff,
        )
        assert finding.suggested_patch.startswith("--- a/Makefile")

    def test_finding_extra_fields_still_rejected(self):
        with pytest.raises(ValidationError):
            Finding(
                rule_id="x",
                pillar=Pillar.FLOW,
                severity=Severity.WARN,
                message="x",
                unknown_extra=True,
            )


class TestSearch:
    def test_request_defaults(self):
        req = SearchRequest(q="large file false positive")
        assert req.k == 5
        assert req.pillar is None

    def test_response(self):
        resp = SearchResponse(hits=[SearchHit(text="hello", source="x", score=0.5)])
        assert resp.protocol_version == PROTOCOL_VERSION
        assert resp.hits[0].score == 0.5


class TestHealth:
    def test_minimal(self):
        h = HealthResponse(engine_version="0.1.0")
        assert h.protocol_version == PROTOCOL_VERSION
        assert h.rules_version_supported == [RULES_VERSION]
        assert h.status == "ok"


class TestSchemaExport:
    def test_committed_schema_exists_and_is_valid_json(self):
        schema_path = Path(__file__).parent.parent / "schemas" / "rule.schema.json"
        assert schema_path.exists(), f"Run `make schema` to regenerate {schema_path}"
        data = json.loads(schema_path.read_text())
        assert "$defs" in data or "properties" in data


# ---------------------------------------------------------------------------
# Action contract (rules_version >= 2)
# ---------------------------------------------------------------------------


def _v2_min_rule_dict(**overrides):
    """Helper: returns a minimal valid rules_version=2 rule dict.

    Saves rebuilding the boilerplate on every test below.
    """
    base = {
        "rules_version": 2,
        "id": "test.minimal",
        "pillar": "feedback",
        "title": "test minimal v2 rule",
        "match": {"type": "path_glob", "require_globs": ["AGENTS.md"]},
        "action": {
            "kind": "create_file",
            "path": "AGENTS.md",
            "template": "# Agents guide\n",
        },
        "verify": {"command": "test -f AGENTS.md", "description": ""},
    }
    base.update(overrides)
    return base


class TestActionContract:
    """``rules_version >= 2`` requires a structured action + verify pair.

    Tests cover the six action kinds, the precondition / context_probe
    decorations, the v2-required validator, and the round-trip via
    serialization helpers.
    """

    def test_create_file_action(self):
        a = CreateFileAction(path="AGENTS.md", template="# Hi\n")
        assert a.kind == "create_file"
        assert a.preconditions == []
        assert a.context_probe == []

    def test_append_to_file_action(self):
        a = AppendToFileAction(
            path="Makefile",
            template="test:\n\t{language_test_command}\n",
            preconditions=[Precondition(exists="Makefile")],
            context_probe=[ContextProbe(detect=ContextProbeKind.PRIMARY_LANGUAGE)],
        )
        assert a.preconditions[0].exists == "Makefile"
        assert a.context_probe[0].detect == ContextProbeKind.PRIMARY_LANGUAGE

    def test_insert_after_action(self):
        a = InsertAfterAction(
            path=".github/workflows/ci.yml",
            after_pattern=r"^name:\s",
            template="\nconcurrency:\n  group: ${{ github.workflow }}\n",
        )
        assert a.after_pattern.startswith("^name:")

    def test_edit_gitignore_action(self):
        a = EditGitignoreAction(entries=[".env", "node_modules/", ".venv/"])
        assert a.kind == "edit_gitignore"
        assert ".env" in a.entries

    def test_edit_gitignore_action_requires_entries(self):
        with pytest.raises(ValidationError):
            EditGitignoreAction(entries=[])

    def test_modify_manifest_field_action(self):
        a = ModifyManifestFieldAction(
            manifest="pyproject.toml",
            field_path="project.scripts.demo",
            value="my_pkg.cli:main",
        )
        assert a.kind == "modify_manifest_field"
        assert a.field_path == "project.scripts.demo"

    def test_run_command_action(self):
        a = RunCommandAction(
            command="gh extension install ...",
            description="install the gh extension",
        )
        assert a.kind == "run_command"

    def test_action_kind_dispatch_via_dict(self):
        rule = Rule.model_validate(
            _v2_min_rule_dict(
                action={
                    "kind": "edit_gitignore",
                    "entries": [".env"],
                }
            )
        )
        assert isinstance(rule.action, EditGitignoreAction)

    def test_action_unknown_kind_rejected(self):
        with pytest.raises(ValidationError):
            Rule.model_validate(
                _v2_min_rule_dict(action={"kind": "wipe_disk"})
            )

    def test_v2_requires_action(self):
        d = _v2_min_rule_dict()
        d.pop("action")
        with pytest.raises(ValidationError) as exc:
            Rule.model_validate(d)
        assert "action" in str(exc.value).lower()

    def test_v2_requires_verify(self):
        d = _v2_min_rule_dict()
        d.pop("verify")
        with pytest.raises(ValidationError) as exc:
            Rule.model_validate(d)
        assert "verify" in str(exc.value).lower()

    def test_v1_does_not_require_action(self):
        # Backward compatibility: legacy YAML still validates.
        rule = Rule.model_validate(
            {
                "rules_version": 1,
                "id": "x",
                "pillar": "flow",
                "title": "x",
                "match": {"type": "file_size"},
            }
        )
        assert rule.action is None
        assert rule.verify is None

    def test_v2_round_trip(self):
        rule = Rule.model_validate(_v2_min_rule_dict())
        s = to_json(rule)
        restored = from_json(Rule, s)
        assert restored.rules_version == 2
        assert isinstance(restored.action, CreateFileAction)
        assert restored.verify.command == "test -f AGENTS.md"

    def test_verify_step_defaults(self):
        v = VerifyStep(command="test -f AGENTS.md")
        assert v.timeout_seconds == 15
        assert v.offline is True

    def test_finding_can_carry_action_and_verify(self):
        f = Finding(
            rule_id="agent_docs.canonical",
            pillar=Pillar.COGNITIVE_LOAD,
            severity=Severity.WARN,
            message="No AGENTS.md present",
            action=CreateFileAction(path="AGENTS.md", template="# Hi\n"),
            verify=VerifyStep(command="test -f AGENTS.md"),
        )
        assert f.action.kind == "create_file"
        assert f.verify.command == "test -f AGENTS.md"

    def test_action_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            CreateFileAction(path="x", template="y", extra_field="boom")

    def test_context_probe_unknown_detect_rejected(self):
        with pytest.raises(ValidationError):
            ContextProbe(detect="invent_a_signal")

    def test_v2_with_preconditions_serialises(self):
        rule = Rule.model_validate(
            _v2_min_rule_dict(
                action={
                    "kind": "append_to_file",
                    "path": "Makefile",
                    "template": "test:\n\tpytest tests/\n",
                    "preconditions": [
                        {"exists": "Makefile"},
                        {"manifest_language": "python"},
                    ],
                    "context_probe": [
                        {"detect": "primary_language"},
                        {"detect": "makefile_targets"},
                    ],
                }
            )
        )
        s = to_json(rule)
        restored = from_json(Rule, s)
        assert isinstance(restored.action, AppendToFileAction)
        assert len(restored.action.preconditions) == 2
        assert restored.action.context_probe[1].detect == ContextProbeKind.MAKEFILE_TARGETS
