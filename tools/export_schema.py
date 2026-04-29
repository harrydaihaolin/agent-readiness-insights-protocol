#!/usr/bin/env python3
"""Dump the Rule pydantic model to schemas/rule.schema.json.

The output is a JSON Schema (draft 2020-12) that the rules-repo CI uses
to validate every YAML rule file before merging. Run via `make schema`
whenever models.Rule changes; commit the regenerated schema.

Output is deterministic: fields sorted, indent=2, trailing newline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = ROOT / "schemas" / "rule.schema.json"

# Make the package importable without install (so the script is runnable
# directly during dev without `pip install -e .`).
sys.path.insert(0, str(SRC))

from agent_readiness_insights_protocol import Rule  # noqa: E402


def main() -> int:
    schema = Rule.model_json_schema(mode="validation")
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    schema.setdefault("$id", "https://github.com/harrydaihaolin/agent-readiness-insights-protocol/schemas/rule.schema.json")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
