# Publishing

The package builds reproducibly via `make build`. Releasing to PyPI is a
two-step process kept manual on purpose because version bumps coordinate
across multiple downstream repos.

## Test PyPI first

Always release to test.pypi.org first to verify the wheel installs cleanly
before pushing to production PyPI.

```bash
make build
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            agent-readiness-insights-protocol==X.Y.Z
```

Smoke-test:

```python
from agent_readiness_insights_protocol import PROTOCOL_VERSION, RULES_VERSION, Rule
print(PROTOCOL_VERSION, RULES_VERSION)
```

## Production PyPI

```bash
twine upload dist/*
```

Then tag:

```bash
git tag v$(python -c "import agent_readiness_insights_protocol as p; print(p.__version__)")
git push --tags
```

## Credentials

A PyPI API token is required. Configure once in `~/.pypirc`:

```ini
[testpypi]
username = __token__
password = pypi-AgENd...

[pypi]
username = __token__
password = pypi-AgENd...
```

## Coordinating bumps

Before bumping `PROTOCOL_VERSION` or `RULES_VERSION`, open a tracking issue
in:

- `harrydaihaolin/agent-readiness` (consumer of `RULES_VERSION`)
- `harrydaihaolin/agent-readiness-rules` (declares `protocol_compat`)
- `harrydaihaolin/agent-readiness-pro` (consumer of `PROTOCOL_VERSION`)
- `harrydaihaolin/agent-readiness-insights` (engine; consumer of both)

Land the bump here last; downstream PRs widen their compat ranges first.
