# Contributing

Thanks for your interest. This is the protocol package — the smallest,
most-stable repo in the agent-readiness ecosystem. Most changes here are
deliberate and require coordination with downstream consumers.

## Before opening a PR

1. Read [`AGENTS.md`](./AGENTS.md) — especially the versioning rules table.
2. Decide whether your change is breaking or non-breaking. If breaking,
   we'll need to bump `PROTOCOL_VERSION` or `RULES_VERSION` and coordinate
   with `agent-readiness`, `agent-readiness-rules`, and the engine.
3. Run `make dev && make test && make lint`.
4. If you touched `models.Rule`, run `make schema` and commit the regenerated
   `schemas/rule.schema.json`.

## What belongs here

- Pydantic dataclasses shared by client + engine + rules + scanner.
- Version constants.
- JSON Schema exports.

## What does not belong here

- HTTP clients (live in `agent-readiness-pro`).
- Match-type implementations (live in `agent-readiness/rules_eval` and the
  engine).
- Rule files (live in `agent-readiness-rules`).
- Tests of downstream behavior (live in their respective repos).

## Releasing

1. Bump `version` in `pyproject.toml`.
2. `make build`.
3. `twine upload dist/*` (or `uv publish`).
4. Tag `git tag v$VERSION && git push --tags`.
