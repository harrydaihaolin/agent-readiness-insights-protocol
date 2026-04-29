"""Version constants for the agent-readiness insights protocol.

These integers are the contract between every consumer of the insights
ecosystem. Bump only on intentional breaking changes; downstream
consumers will pin against them.

`PROTOCOL_VERSION`
    Schema version for JSON shapes used over the wire (`/evaluate`,
    `/insights/search`, `/healthz` request/response bodies). Adding
    optional fields is non-breaking and does NOT bump this.

`RULES_VERSION`
    Schema version for the YAML rule format (match types, required
    fields). Each YAML rule file declares `rules_version: N` at its
    top level. Loaders refuse rules whose `rules_version` is outside
    their supported range.

These two versions evolve independently. The engine's `/healthz`
reports both so a client can decide how to behave on mismatch.
"""

from __future__ import annotations

PROTOCOL_VERSION: int = 1
RULES_VERSION: int = 1

__all__ = ["PROTOCOL_VERSION", "RULES_VERSION"]
