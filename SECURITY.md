# Security policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.x     | yes       |

## Reporting a vulnerability

Email security reports to the maintainers via GitHub Security Advisories
on this repository. Do not open public issues for security problems.

This package contains no I/O, no network calls, and no code execution —
the attack surface is limited to deserialization of untrusted JSON via
pydantic. We will respond to triaged reports within 7 days.
