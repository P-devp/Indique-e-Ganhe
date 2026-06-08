.PHONY: dev test lint typecheck coverage install install-dev serve clean

# ── Development ────────────────────────────────────────────────

dev:
	cd backend && python app.py

serve:
	python run.py

install:
	pip install -r backend/requirements.txt

install-dev:
	pip install -r backend/requirements.txt
	pip install ruff mypy pytest-cov pre-commit playwright
	playwright install chromium

# ── Quality ────────────────────────────────────────────────────

lint:
	cd backend && ruff check .

lint-fix:
	cd backend && ruff check --fix .

format:
	cd backend && ruff format .

typecheck:
	cd backend && mypy app.py database.py --ignore-missing-imports

clean:
	cd backend && rmdir /s /q __pycache__ .pytest_cache 2>nul || exit 0

# ── Testing ────────────────────────────────────────────────────

test:
	cd backend && python -m pytest -v

test-coverage:
	cd backend && python -m pytest --cov --cov-report=term --cov-report=html

test-integration:
	cd backend && python -m pytest tests/ -v -m integration

# ── Pre-commit ─────────────────────────────────────────────────

pre-commit-install:
	pre-commit install

pre-commit-run:
	pre-commit run --all-files
