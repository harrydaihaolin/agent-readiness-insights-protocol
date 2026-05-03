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

PROTOCOL_VERSION: int = 2
RULES_VERSION: int = 2

# Engines accept rules with this version OR lower during the v1 -> v2
# transition window so downstream consumers don't break the day v2 ships.
# v1 rules are required to carry a fix_hint; v2 rules MUST carry the
# structured action + verify blocks. Removed in a future v3 cleanup once
# the rules pack is fully migrated.
RULES_VERSION_MIN_SUPPORTED: int = 1

__all__ = [
    "PROTOCOL_VERSION",
    "RULES_VERSION",
    "RULES_VERSION_MIN_SUPPORTED",
]
