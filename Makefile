# Tareas comunes del proyecto. La CI llama a los mismos targets que se usan en local.
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS += --warn-undefined-variables --no-builtin-rules

# --locked: falla si pyproject.toml y uv.lock no cuadran, en vez de actualizar el lock en silencio.
UV_RUN := uv run --locked

.PHONY: help setup lint test format check

help: ## Muestra los targets disponibles
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-8s %s\n", $$1, $$2}'

setup: ## Crea el entorno con uv e instala los hooks de git
	uv sync --locked
	$(UV_RUN) prek install

lint: ## Comprueba formato, lint, tipos y workflows sin modificar ficheros
	$(UV_RUN) ruff format --check .
	$(UV_RUN) ruff check .
	$(UV_RUN) mypy
	$(UV_RUN) zizmor --no-progress --strict-collection .

test: ## Ejecuta los tests
	$(UV_RUN) pytest

# Primero los arreglos de ruff check, porque pueden dejar código que el formateador recoloca.
format: ## Aplica los arreglos automáticos de ruff y formatea (modifica ficheros)
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

check: lint test ## Lint y tests, como en la CI
