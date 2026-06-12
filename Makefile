.DEFAULT_GOAL := help

.PHONY: help setup run clean CI build kill

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
	. .venv/bin/activate && python -m playwright install chromium
	npm install
	mkdir -p data/parquet data/manifests data/exports data/config data/runtime

run:
	. .venv/bin/activate && python scripts/run_app.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov build dist frontend/dist desktop/build desktop/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -f .coverage data/runtime/*.pid

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
	. .venv/bin/activate && python scripts/scan_no_secrets.py
	. .venv/bin/activate && bandit -q -c bandit.yml -x backend/tests -r backend desktop scripts

build:
	npm run build
	. .venv/bin/activate && python scripts/build_desktop.py

kill:
	python scripts/kill_app.py
