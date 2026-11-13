# Repository structure

This repository contains two applications. The backend uses FastAPI and SQLite;
the frontend uses native browser JavaScript modules and CSS. No frontend build
tool or JavaScript framework is required.

```text
backend/
  app/
    main.py                 Application factory, middleware and worker lifecycle
    api/
      routes/               Health, questionnaire, sessions, generations, staff API
      dependencies.py       Kiosk and staff authentication
      schemas.py            HTTP request validation
      presenters.py         Public response formatting and shared HTTP lookups
    core/config.py          Environment settings and repository paths
    domain/                 Questionnaire, answer validation and design prompts
    services/worker.py      Generation queue processing and retry orchestration
    providers/              Image adapters, shared contracts and provider factory
    repositories/storage.py SQLite access, archive persistence and integrity checks
  tests/                    Backend and frontend asset integration tests
  pyproject.toml            Python package metadata and development dependencies
  requirements*.txt         Backend and isolated model runtime dependencies
  Dockerfile*               Lightweight, CPU and NVIDIA backend images
frontend/
  index.html                Browser document
  src/
    main.js                 Frontend entry point
    api/client.js           HTTP client and API error handling
    state/session.js        Shared experience state and persistence key
    components/icons.js     Shared SVG icons
    features/stadium/
      controller.js         Visitor actions, API orchestration and job polling
      views.js              Stadium experience rendering and selection rules
    lib/html.js             HTML escaping
    styles/main.css         Application styles
  docker/nginx.conf         Static serving and backend proxy
  Dockerfile                Frontend image
scripts/                    Launch, model setup, demo and backup commands
docs/                       Architecture and API reference
compose.dev.yaml            Local Docker stack
compose.prod.yaml           NVIDIA server stack
pytest.ini                  Test discovery from repository root
```

## Adding features

Backend HTTP handlers belong in `backend/app/api/routes/`. Add request schemas
to `api/schemas.py`; put reusable business rules in `domain/`, orchestration in
`services/`, and database/archive behavior in `repositories/`. Register new routers
in `app/main.py`. Keep provider-specific SDKs, HTTP requests and model execution
inside `providers/`; use `Generation` and `ProviderError` from `providers/base.py`
and register adapters in `providers/factory.py`. Heavy model imports remain lazy.

Frontend features belong in `frontend/src/features/<feature>/`, with controllers
handling interactions and views rendering the UI. Shared UI code belongs in
`components/`, general helpers in `lib/`, and HTTP handling in `api/`. Use explicit
relative ES module imports. All API requests remain on the same origin, so native
FastAPI serving and the NGINX proxy use the same browser code.

The existing endpoint URLs and request/response formats are preserved. The backend
still runs exactly one worker process per data directory; do not increase Uvicorn
workers or backend replicas against the same SQLite archive.

## Local setup and commands

Run these commands from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e ./backend
.venv/bin/python -m pytest -q
./scripts/run.sh mps
```

For an existing checkout after this folder migration, refresh the editable
installation once with `.venv/bin/python -m pip install --no-build-isolation --no-deps -e ./backend`.
The mode selector also sets the backend import path explicitly. A direct mock run is:

```sh
GENERATION_PROVIDER=mock .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

Settings continue to load the repository-root `.env`, independent of the current
working directory. `.venv/`, `.venv-flux/`, `models/`, `data/` and local environment
files stay in their existing root locations and remain ignored by Git. Refactoring
does not require downloading models again or moving saved designs.

## Containers

Both Compose files stay at the repository root. Backend builds use that root as
their context because native serving includes the frontend assets too. Backend
images retain `/app` as the repository root and add `/app/backend` to `PYTHONPATH`.
Frontend builds use `frontend/` as their context and copy `index.html` and `src/`.

```sh
docker compose -f compose.dev.yaml up --build -d
docker compose --env-file .env.server -f compose.prod.yaml up --build -d
```

Existing Compose project names, volume names and model mounts are retained. See
the root README for model preparation, server configuration, backup and restore.
