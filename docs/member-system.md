# Member System Runbook

## Install

```bash
make install
```

## Run

```bash
make run-backend
```

Auth for local testing uses request headers:

- `X-User-Id`
- `X-Role` with `user` or `admin`
- optional `X-Request-Id`

## Test

```bash
make test
make test-unit
make test-integration
make test-e2e
```
