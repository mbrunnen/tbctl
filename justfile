default: install

generate:
    ./generate.sh

sync:
    uv sync

install:
    uv tool install --reinstall .

test:
    uv run pytest

cov:
    uv run pytest --cov=tbctl --cov-report=term-missing

lint:
    uv run ruff check tbctl/ tests/
    uv run ruff format --check tbctl/ tests/

fmt:
    uv run ruff check --fix tbctl/ tests/
    uv run ruff format tbctl/ tests/
