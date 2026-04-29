"""Tests for the protocol dataclasses, version constants, and serializers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_readiness_insights_protocol import (
    PROTOCOL_VERSION,
    RULES_VERSION,
    CompositeMatch,
    EvaluateRequest,
    EvaluateResponse,
    FileSizeMatch,
    Finding,
    HealthResponse,
    Insight,
    ManifestFieldMatch,
    PathGlobMatch,
    Pillar,
    RegexInFilesMatch,
    Rule,
    SearchHit,
    SearchRequest,
    SearchResponse,
    Severity,
    from_json,
    to_json,
)


class TestVersionConstants:
    def test_protocol_version_is_one(self):
        assert PROTOCOL_VERSION == 1

    def test_rules_version_is_one(self):
        assert RULES_VERSION == 1


class TestRule:
    def test_minimal_rule_with_file_size_match(self):
        rule = Rule(
            id="repo_shape.large_files",
            pillar=Pillar.COGNITIVE_LOAD,
            title="Large files",
            match=FileSizeMatch(),
        )
        assert rule.rules_version == RULES_VERSION
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
