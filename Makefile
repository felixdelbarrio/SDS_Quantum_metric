.DEFAULT_GOAL := help

CODEQL_VERSION ?= latest
CODEQL_HOME ?= .tools/codeql
CODEQL ?= $(CODEQL_HOME)/codeql
CODEQL_DB_DIR ?= .codeql-db
CODEQL_SOURCE_DIR ?= .codeql-source
CODEQL_PYTHON_DB ?= $(CODEQL_DB_DIR)/python
CODEQL_TS_DB ?= $(CODEQL_DB_DIR)/javascript-typescript

.PHONY: help setup run clean CI build kill _codeql _codeql-clean

help:
	@printf "Targets disponibles:\\n"
	@printf "  make setup  Instala dependencias y prepara data local\\n"
	@printf "  make run    Levanta backend, frontend y visor desktop\\n"
	@printf "  make clean  Limpia caches/builds sin borrar Parquet\\n"
	@printf "  make CI     Ejecuta checks backend/frontend/security\\n"
	@printf "  make build  Genera artefacto desktop local\\n"
	@printf "  make kill   Detiene procesos iniciados por make run\\n"

setup:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip
	. .venv/bin/activate && python -m pip install -e ".[dev,desktop]"
	. .venv/bin/activate && python scripts/ensure_playwright_browsers.py
	npm install
	. .venv/bin/activate && python scripts/setup_codeql.py --version "$(CODEQL_VERSION)" --home "$(CODEQL_HOME)"
	mkdir -p data/parquet data/manifests data/exports data/config data/runtime

run:
	. .venv/bin/activate && python scripts/run_app.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov build dist frontend/dist desktop/build desktop/dist $(CODEQL_DB_DIR) $(CODEQL_SOURCE_DIR)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -f .coverage data/runtime/*.pid codeql-results*.sarif

CI:
	. .venv/bin/activate && ruff format --check backend desktop scripts
	. .venv/bin/activate && ruff check backend desktop scripts
	. .venv/bin/activate && mypy backend desktop
	. .venv/bin/activate && coverage run -m pytest
	. .venv/bin/activate && coverage report
	npm run format:check
	npm run lint
	npm run typecheck
	npm test
	npm run build
	. .venv/bin/activate && python scripts/scan_no_secrets.py
	. .venv/bin/activate && bandit -q -c bandit.yml -x backend/tests -r backend desktop scripts
	. .venv/bin/activate && python scripts/smoke_test_desktop.py --preflight
	$(MAKE) _codeql

_codeql:
	. .venv/bin/activate && python scripts/setup_codeql.py --version "$(CODEQL_VERSION)" --home "$(CODEQL_HOME)"
	rm -rf "$(CODEQL_PYTHON_DB)" "$(CODEQL_TS_DB)" "$(CODEQL_SOURCE_DIR)" codeql-results-python.sarif codeql-results-javascript-typescript.sarif
	mkdir -p "$(CODEQL_DB_DIR)" "$(CODEQL_SOURCE_DIR)"
	git ls-files -z --cached --others --exclude-standard | perl -0ne 'print if -e $$_' | rsync -a --files-from=- --from0 ./ "$(CODEQL_SOURCE_DIR)"
	"$(CODEQL)" database create "$(CODEQL_PYTHON_DB)" --language=python --source-root="$(CODEQL_SOURCE_DIR)" --overwrite
	"$(CODEQL)" database analyze "$(CODEQL_PYTHON_DB)" codeql/python-queries --format=sarif-latest --output=codeql-results-python.sarif
	"$(CODEQL)" database create "$(CODEQL_TS_DB)" --language=javascript-typescript --source-root="$(CODEQL_SOURCE_DIR)" --overwrite
	"$(CODEQL)" database analyze "$(CODEQL_TS_DB)" codeql/javascript-queries --format=sarif-latest --output=codeql-results-javascript-typescript.sarif

_codeql-clean:
	rm -rf "$(CODEQL_DB_DIR)" "$(CODEQL_SOURCE_DIR)"
	rm -f codeql-results*.sarif

build:
	npm run build
	. .venv/bin/activate && python scripts/build_desktop.py
	. .venv/bin/activate && python scripts/smoke_test_desktop.py

kill:
	python scripts/kill_app.py
