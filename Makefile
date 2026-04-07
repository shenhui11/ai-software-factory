install:
	pip install -r requirements.txt || true
	npm ci || true

test-unit:
	pytest tests/unit -q

test-integration:
	pytest tests/integration -q

test-e2e:
	npx playwright test

lint:
	ruff check .
	eslint . || true

format:
	ruff format .
	prettier --write . || true
