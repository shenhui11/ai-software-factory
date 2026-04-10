install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

run-backend:
	uvicorn apps.backend.main:app --host 0.0.0.0 --port 8000

test:
	pytest -q

test-unit:
	pytest tests/unit -q

test-integration:
	pytest tests/integration -q

test-e2e:
	npx playwright test

lint:
	ruff check .

format:
	ruff format .
