PYTHON ?= python3
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
export UV_CACHE_DIR
PY := .venv/bin/python
CLI := $(PY) -m orchestrator.cli

.PHONY: setup quickstart demo-bootstrap demo-greenfield demo-brownfield demo-ambiguous serve smoke lint typecheck test check evidence security contract
setup:
	uv sync --frozen --extra dev --python $(PYTHON)

quickstart: setup
	$(PY) scripts/http_smoke.py
	$(CLI) demo greenfield

demo-bootstrap:
	$(PY) scripts/demo.py

demo-greenfield:
	$(CLI) demo greenfield

demo-brownfield:
	$(CLI) demo brownfield

demo-ambiguous:
	$(CLI) demo ambiguous

serve:
	$(PY) -m shortener

smoke:
	$(PY) scripts/http_smoke.py

lint:
	.venv/bin/ruff check orchestrator shortener tests scripts alembic
	.venv/bin/ruff format --check orchestrator shortener tests scripts alembic

typecheck:
	.venv/bin/mypy orchestrator shortener

test:
	$(PY) -m pytest --cov=orchestrator --cov=shortener --cov-report=term-missing --cov-report=json:runs/evidence/coverage.json --cov-report=html:runs/evidence/htmlcov

security:
	$(PY) -m pytest tests/security -q

contract:
	$(PY) -m pytest tests/test_contract.py -q

check: lint typecheck test

evidence:
	$(PY) scripts/evidence.py final-checks make check
	$(PY) scripts/evidence.py final-security make security
	$(PY) scripts/evidence.py final-contract make contract
	$(PY) scripts/evidence.py final-http make smoke
	$(PY) scripts/evidence.py final-greenfield make demo-greenfield
	$(PY) scripts/evidence.py final-brownfield make demo-brownfield
	$(PY) scripts/evidence.py final-ambiguous make demo-ambiguous
