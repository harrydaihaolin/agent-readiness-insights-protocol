# Agent guide

Conventions for AI coding agents working in this repository.

## Canonical commands

- Install dev deps: `make dev`
- Run tests:        `make test`
- Lint:             `make lint`
- Regenerate schema: `make schema`
- Build wheel:      `make build`

The package is pure data + dataclasses. No CLI, no I/O, no network calls.
Everything is JSON-serialisable via pydantic.

## Source of truth

- `src/agent_readiness_insights_protocol/version.py` — `PROTOCOL_VERSION`
  and `RULES_VERSION`. These are the contract. Bump only on intentional
  breaking changes; consumers will pin against them.
- `src/agent_readiness_insights_protocol/models.py` — pydantic dataclasses.
  Adding optional fields is non-breaking. Renaming or removing fields is
  breaking.
- `schemas/rule.schema.json` — generated from `models.Rule` via
  `tools/export_schema.py`. Regenerate before commit if `Rule` changes.

## Versioning rules (the only thing that really matters here)

| Change | Version bump |
|---|---|
| Add optional field to a model | none |
| Add new optional field to JSON response | none |
| Rename / remove field | major (1 → 2) |
| Change field type semantics | major |
| Add new model | none |
| Add new match type to `Rule.match.type` enum | minor at most; runtime should accept-and-skip-unknown |

## Do-not-touch (without a clear reason)

- `version.py` integers — coordinated bump only.
- The `model_config` of `Rule` and friends — `extra="forbid"` keeps consumers
  honest. Never relax to `"allow"` without a major version bump.

## Style

- Pydantic v2 only. No dataclasses, no attrs, no manual `__init__`.
- Type-annotated, `from __future__ import annotations` at the top of modules.
- One model per concept. Compose with other models, don't subclass.
