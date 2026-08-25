# Contributing to ORION

Thanks for your interest in contributing! This document covers the basics.

## Development setup

```bash
git clone <your-fork-url> && cd Trade
cp .env.example .env          # then edit .env (generate SECRET_KEY!)
docker compose build
make migrate
make run                      # http://localhost:8080
```

Generate a development secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Ground rules

1. **No secrets in source.** CI runs gitleaks and will fail the pipeline.
   All configuration flows through environment variables (see `.env.example`).
2. **Type safety everywhere.** Backend: Pydantic v2 schemas for every
   request/response. Frontend: zod validation of every API payload.
3. **Every response uses the envelope** `{status, data, message, timestamp}`.
4. **Parameterized queries only** - never string-format SQL.
5. **Tests required.** New business logic needs unit tests; keep overall
   coverage at or above 85% (`make test` enforces this locally too).
6. **Free data sources only.** New integrations must not require paid API
   keys, and must implement a graceful fallback.

## Before opening a PR

```bash
make lint            # flake8 + eslint + tsc
make test            # pytest, >=85% coverage
make security-check  # gitleaks + pip-audit + npm audit
```

## Commit style

Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
`chore:`) keep the changelog tidy.

## Reporting security issues

Please do NOT open a public issue for vulnerabilities. See
`CODE_OF_CONDUCT.md` for contact expectations, or use a private security
advisory via GitHub's "Report a vulnerability" feature.
