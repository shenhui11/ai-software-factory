# FEAT-0002 Run Guide

## Install

```bash
make install
```

## Run Backend

```bash
make run-backend
```

## Run Tests

```bash
pytest -q
pytest tests/unit/test_member_services.py -q
pytest tests/integration/test_member_system.py -q
```
