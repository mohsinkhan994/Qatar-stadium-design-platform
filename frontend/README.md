# Frontend

Static HTML, CSS and native JavaScript modules. `src/main.js` starts the stadium
feature controller; `src/features/stadium/` owns its views and interactions.
Shared HTTP, state, icons and HTML helpers have separate modules under `src/`.

Run the whole app from the repository root with `./scripts/run.sh mps` or
`docker compose -f compose.dev.yaml up --build -d`. FastAPI serves this directory
in native Mac mode; NGINX serves it and proxies API requests in Docker. No Node
installation or frontend dependency installation is needed to run the app.

See [the architecture guide](../docs/architecture.md) for extension conventions.
