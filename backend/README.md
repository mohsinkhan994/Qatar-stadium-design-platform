# Backend

FastAPI application with domain rules, API routers, generation services, provider
adapters and archive persistence in separate packages under `app/`. Tests live in
`tests/`; dependency files and backend Dockerfiles belong to this directory.

Install from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e ./backend
.venv/bin/python -m pytest -q
```

The root `scripts/run.sh` manages native Mac and Docker modes. Environment files,
model caches and persistent data remain at the repository root. Dockerfiles use
the repository root as their build context, as configured in both Compose files.

See [the architecture guide](../docs/architecture.md) for module responsibilities.
