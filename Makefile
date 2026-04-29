.PHONY: install dev test lint schema clean build

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	PYTHONPATH=src python3 -m pytest tests/ -v

lint:
	ruff check src tests tools

schema:
	PYTHONPATH=src python3 tools/export_schema.py

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

build: clean schema
	python3 -m build
