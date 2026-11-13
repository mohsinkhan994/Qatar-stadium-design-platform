# Qatar Stadium Design Platform

Working prototype for the QMA “Design Your Own Stadium” questionnaire.
Python 3.11+ / FastAPI / SQLite, with a separately containerised static frontend.

Application code is separated into `backend/` and `frontend/`. See the
[architecture guide](docs/architecture.md) for the folder structure and where to
add new features, and the application guides in
[backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md).

Two standalone Compose files cover the supported environments:

- `compose.dev.yaml`: Mac Docker Desktop, using CPU, mock, or API generation.
- `compose.prod.yaml`: Linux server with NVIDIA CUDA, serving both kiosks.

For the faster native Mac GPU path, use `./scripts/run.sh mps`. MPS runs outside
Docker; it does not require another Compose file.

## Generation quality and benchmarking

The [generation pipeline guide](docs/generation-quality.md) covers structured
architectural captions, persistent MLX inference, resolution profiles, optional
local visual evaluation, curated reference images, bounded retries and benchmark
commands. Visual scores remain unavailable until a real image evaluator is configured.

## Run on your Mac

This checkout already has a `.venv` with dependencies installed. From this directory:

```sh
./scripts/run.sh
```

Choose Docker CPU, native Mac MPS, or an OpenAI/Gemini API key. The launcher
starts the selected backend and prints its app URL. MPS runs natively at
<http://127.0.0.1:8000/>; Docker and API modes run at <http://localhost:3000/>.
MPS runs in the foreground; press Ctrl+C before selecting another mode.
`./scripts/run.sh stop` stops MPS from another terminal and stops the Docker stack.
Docker archives use the `stadium-data` volume; native MPS archives use `./data`,
so those histories are separate. For API mode, add a key to `.env` first. Keys
stay on the backend.

To start the mock backend directly instead of using the mode selector:

```sh
cp -n .env.example .env
# Edit .env if you want cloud generation. The default is a free test schematic.
GENERATION_PROVIDER=mock .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

On a fresh machine, install Python 3.11 or newer and run these first:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e ./backend
```

Use **one** uvicorn worker. Do not run another instance with the same `DATA_DIR`.
Do not use `--reload` during a paid image generation: restarting can interrupt it.
Keep this prototype bound to localhost. Network deployment needs explicit host
allowlisting, authentication, HTTPS, rate controls and an operating-system kiosk setup.

- Touchscreen experience: <http://127.0.0.1:8000/>
- Interactive API documentation: <http://127.0.0.1:8000/docs>
- API schema: <http://127.0.0.1:8000/openapi.json>
- Health and capabilities: <http://127.0.0.1:8000/health>

The Swagger documentation loads its JavaScript from a CDN; the API itself and mock
workflow operate without internet. `openapi.json` is also checked into `docs/`.

Run a complete sample session in another terminal:

```sh
.venv/bin/python scripts/demo.py
```

The script prints the image URL, result and verified archive reference. In mock
mode the image is visibly labelled **TEST SCHEMATIC — NOT AI GENERATED**. It is a
development fixture, not the museum's required offline-generation demonstration.

## FLUX 3 Image Klein on your Mac

The local provider now uses the distilled FLUX 3 Image Klein checkpoint (16 steps).
On Apple Silicon it runs with MLX/Metal in an isolated `.venv-flux`, using a saved
4-bit model at `models/flux3-image-klein-q4`. The backend keeps its own `.venv`;
MLX's Pillow 13 and other dependencies do not replace backend packages.

Before the first download, accept the model conditions at
<https://huggingface.co/black-forest-labs/flux-3-image-klein> and authenticate with `hf auth login` (a read token is sufficient).
If no Hugging Face CLI is installed yet, run setup to install the runtime, then
use `.venv-flux/bin/hf auth login` and rerun setup. Do not paste the token into chat.
Stop an existing image-generation server before converting weights so GPU memory
is available. From this project directory:

```sh
./scripts/run.sh stop
./scripts/setup_flux.sh
./scripts/run.sh mps
```

Open <http://127.0.0.1:8000/>. Setup downloads the pinned [MFLUX community q4 conversion](https://huggingface.co/mflux-community/flux-3-image-klein-mflux-q4)
(about 5.3 GB). The original model license applies. Allow at least 10 GB free disk
space for weights and runtime dependencies. Download time depends on the connection. To resume the chunks from the initial
installation, run `.venv/bin/python scripts/download_flux_parallel.py --workers 16`
before rerunning `./scripts/setup_flux.sh`. This reuses completed parts and verifies
each weight file against its published SHA256 checksum. The default output
is 1024×576 at 16 steps. The distilled model uses no classifier-free guidance
or negative prompt. Quantization reduces memory, with some loss of fine detail.
Close other memory-heavy apps on the 24 GB Mac.

Generation uses a separate MLX process per job, so weights load for each image and
GPU memory is released afterward. The app queues requests as before. The runtime
uses offline mode after setup; no image API key is used. The questionnaire is
expanded into a full scene caption containing every selected answer, rather than
the old shortened SDXL caption. No additional prompt-expander model is downloaded.

The model's [FLUX Kommunity License](https://huggingface.co/black-forest-labs/flux-3-image-klein/blob/main/LICENSE.md)
has conditions for commercial use. Confirm the client's eligibility before deploying.

## Run with Docker Compose

Start Docker Desktop, then run from this directory (Compose 2.24+):

```sh
cp -n .env.example .env
docker compose -f compose.dev.yaml up --build -d
docker compose -f compose.dev.yaml ps
```

Open the touchscreen app at <http://localhost:3000/>. The backend and API docs
remain at <http://localhost:8001/> and <http://localhost:8001/docs>. Set
`FRONTEND_PORT` or `BACKEND_PORT` in `.env` to change their host ports. The frontend
proxies `/health` and `/api/*` over Compose's private network; the backend does not
need to be exposed to other machines. Both containers run on Apple Silicon. The development backend includes the local
CPU model dependencies; set `GENERATION_PROVIDER=local` for CPU inference, or select
mock/cloud generation through `.env`.

```sh
# Logs
docker compose -f compose.dev.yaml logs -f backend
# Frontend and backend logs together
docker compose -f compose.dev.yaml logs -f frontend backend
# Complete a free mock session inside the container
docker compose -f compose.dev.yaml exec backend python scripts/demo.py
# Stop while preserving sessions and archives
docker compose -f compose.dev.yaml down
```

For cloud generation, configure `.env` as below, run `docker compose -f compose.dev.yaml up -d` to
recreate the container with the new configuration, and deliberately opt into a
billable demo with `docker compose -f compose.dev.yaml exec backend python scripts/demo.py --allow-paid`.
Keys are injected at runtime; `.env`, native data and the Mac virtual environment
are excluded from the Docker build context.

The `stadium-data` named volume stores the database and archive at `/app/data`.
It survives container recreation and ordinary `docker compose -f compose.dev.yaml down`. **Do not use
`docker compose -f compose.dev.yaml down -v` unless you intend to delete the Docker archive.** The
volume starts separately from your native `./data` directory; existing Mac demo
records are not automatically imported. Keep one backend replica per volume.

The frontend image uses the official unprivileged NGINX image, serves only the
three static web assets, and proxies health and API paths to the backend service.
Both containers publish only to localhost. The service runs as a non-root user and has a health
check and automatic restart policy. Its default 35-minute shutdown grace period
allows slow CPU inference to finish. Configure `DEV_GENERATION_TIMEOUT_SECONDS`
and `LOCAL_BACKEND_STOP_GRACE_PERIOD` together when changing the CPU time limit.

### Local image generation inside Docker

`compose.dev.yaml` supports CPU, mock and API providers. Native MLX/Metal is the
recommended Mac demo path; Docker Desktop cannot use the Apple GPU. The FLUX 3
CPU path uses the full Diffusers model, needs substantially more memory than the
quantized Mac path, and is not recommended on this 24 GB Mac. Use mock mode for
container UI development:

```sh
GENERATION_PROVIDER=mock docker compose -f compose.dev.yaml up --build -d
```

For a suitably sized CPU host, provision the Diffusers cache first:

```sh
.venv-flux/bin/python scripts/download_flux.py --cuda
GENERATION_PROVIDER=local docker compose -f compose.dev.yaml up --build -d
```

The CUDA-format cache is also used by Diffusers on CPU. The MLX quantized package
is a different format and cannot be mounted as a Diffusers model.

To make a verified Docker backup, stop generation first and run:

```sh
mkdir -p backups
docker compose -f compose.dev.yaml stop backend
docker compose -f compose.dev.yaml run --rm --no-deps -v "$PWD/backups:/backups" backend \
  python scripts/backup.py /app/data /backups/demo-001
docker compose -f compose.dev.yaml up -d
```

For restore, first make a backup of any existing archive. Stop the service, use the
same tool to restore a trusted backup into a new directory within the volume, and
then change Compose's `DATA_DIR` to that directory:

```sh
docker compose -f compose.dev.yaml stop backend
docker compose -f compose.dev.yaml run --rm --no-deps -v "$PWD/backups:/backups" backend \
  python scripts/backup.py /backups/demo-001 /app/data/restored-001
# In compose.dev.yaml, change DATA_DIR to /app/data/restored-001, then:
docker compose -f compose.dev.yaml up -d
```

Both backup and restore destinations must not already exist. After a restore,
use the configured restored directory as the source for subsequent backups.

### Compose deployment and image generation

Use Docker Compose to run the frontend and backend together. Keep
`GENERATION_PROVIDER=mock` for free UI development; the result is the labelled
test schematic. For the Mac AI demo, use the native MLX setup above. For a deployed kiosk that needs faster generation, configure an image
provider in `.env` (`openai` or `gemini`) with an API account funded by the client,
or use a GPU-backed local inference service on a Linux/NVIDIA host. The provider
key remains in the backend environment; the frontend does not need changes. Docker
can expose a GPU to a Compose service when the host and daemon support it
([GPU Compose setup](https://docs.docker.com/compose/how-tos/gpu-support/)).

### Deploy to two kiosks on a Linux NVIDIA server

`compose.prod.yaml` is the server deployment stack. It runs one frontend, one
backend worker, and one local FLUX 3 Image Klein model on one NVIDIA GPU. Both kiosks use the
same server URL; image jobs are queued and generated one at a time to keep GPU
memory use predictable. No OpenAI or Google key is used.

The server needs Linux x86_64, Docker Compose, an NVIDIA GPU and driver, and the
NVIDIA Container Toolkit. Install the host driver and toolkit using the
[NVIDIA installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
The CUDA PyTorch image defaults to `pytorch/pytorch:2.14.1-cuda12.6-cudnn9-runtime`;
if the server driver requires a different CUDA level, change
`PYTORCH_CUDA_IMAGE` in `.env.server` to a compatible official PyTorch runtime image.

The model weights are not included in Git. Copy this checkout's
`models/flux3-hub/` Diffusers cache to the same path on the server before starting the
stack. Provision this cache on the Mac or another authenticated machine first:

```sh
.venv-flux/bin/python scripts/download_flux.py --cuda
```

This downloads the Diffusers transformer/autoencoder layout. The saved MLX q4
package cannot be used by the CUDA pipeline. CUDA currently loads BF16 weights;
GPU memory use has not been measured on the target server. From the Mac:

```sh
rsync -a --progress models/flux3-hub/ user@server:/srv/stadium/models/flux3-hub/
```

Keep the Hugging Face cache's symlinks intact when copying. The container mounts
the cache read-only and runs with
`LOCAL_IMAGE_LOCAL_FILES_ONLY=true`, so generation does not call an external
model service or download weights at runtime.

On the server, from the project directory:

```sh
cp .env.server.example .env.server
# Ensure /srv/stadium/models/flux3-hub/ contains the copied model cache.
# Set MODEL_CACHE_DIR=/srv/stadium/models/flux3-hub in .env.server if needed.
docker compose --env-file .env.server -f compose.prod.yaml config --quiet
docker compose --env-file .env.server -f compose.prod.yaml up --build -d
docker compose --env-file .env.server -f compose.prod.yaml ps
```

The two kiosks open `http://<server-ip>:8080/`. The frontend port binds to all
server interfaces by default. Restrict it with the server firewall to the kiosk
network, or set `FRONTEND_BIND_IP=127.0.0.1` and put a TLS reverse proxy in front.
The backend port is private to the Compose network and is not published on the
host.

Verify that the container sees the GPU:

```sh
docker compose --env-file .env.server -f compose.prod.yaml exec backend \
  python -c 'import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))'
```

The `stadium-data` volume keeps the database and generated archive. Ordinary
`docker compose --env-file .env.server -f compose.prod.yaml down` preserves it; do not add `-v` unless you intend to delete
the archive. For two kiosks this stack deliberately uses one backend replica and
one generation worker. Requests can wait in the queue while another image is
being generated.

## Cloud configuration

Put your key in `.env` locally. Do not paste it into chat, commit it, expose it in
the frontend, or put it in a URL. Restart the backend after changing configuration.
API keys are never written into archive manifests.

OpenAI:

```dotenv
GENERATION_PROVIDER=openai
OPENAI_API_KEY=your-key-here
OPENAI_IMAGE_MODEL=gpt-image-1.5
OPENAI_IMAGE_SIZE=1536x1024
OPENAI_IMAGE_QUALITY=medium
```

Google Nano Banana:

```dotenv
GENERATION_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
GEMINI_IMAGE_MODEL=gemini-nano-banana-2.1
GEMINI_IMAGE_SIZE=2K
```

Select an API-backed Compose run with `./scripts/run.sh api openai` or
`./scripts/run.sh api gemini` after filling the matching key in `.env`.

The OpenAI adapter uses `POST /v1/images/generations`; the Google adapter uses
`POST /v1beta/interactions` with API revision `2026-05-20`. Models are configurable,
but must support the adapter's request format and output settings. These defaults
are starting points, not a claim that either provider is the best choice.

Provider references checked during implementation:

- <https://developers.openai.com/api/reference/resources/images/methods/generate>
- <https://aistudio.google.com/docs/image-generation>

To deliberately run the billable sample workflow:

```sh
.venv/bin/python scripts/demo.py --allow-paid
```

Cloud integration tests simulate HTTP responses. A real provider/account test is
still required. No API key or paid cloud request was used to validate this build.
Timeouts and API failures are not automatically retried because a request may
already have incurred a charge. Exact duplicate images may trigger another attempt
up to `MAX_GENERATION_ATTEMPTS` (default 2 total attempts). No silent fallback to
mock output occurs when a real provider fails.

## Visitor frontend

The touchscreen interface is a dependency-free, responsive web app served by
FastAPI at `/`. It walks visitors through one question at a time, saves each step
to the backend, supports edits and review, asks before accepting compatibility
notes, polls generation status, shows the final image and archive reference, and
verifies the archive before finishing. Session and pending-job IDs survive browser
refreshes in local storage; no participant identity is requested. Option cards
use local SVG icons, and typography uses system fonts, so the experience itself
does not rely on third-party assets or a frontend build step.

The current screen is an English prototype. Custom signature text stays hidden
when moderation is disabled, and the mock provider is clearly identified as a
schematic. For Docker, `docker compose -f compose.dev.yaml up --build -d` rebuilds the image with the
frontend. For native development, run uvicorn using the existing command; the app
serves the same files from `frontend/`.

## Frontend API contract

All paths below start with `/api/v1`. Optional visitor authentication uses
`Authorization: Bearer <KIOSK_API_KEY>`. Staff endpoints use `X-Admin-Key` and are
disabled until `ADMIN_API_KEY` is set. Generate a staff key with:

```sh
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

| Method and path | Purpose |
| --- | --- |
| `GET /questionnaire` | All 15 questions, stable IDs, options and selection limits |
| `POST /sessions` | Create an anonymous session; body `{"language":"en"}` |
| `GET /sessions/{id}` | Resume choices, revision and generation history |
| `PATCH /sessions/{id}/answers` | Merge draft answers with optimistic concurrency |
| `GET /sessions/{id}/review` | Validate completeness and return notes to confirm |
| `POST /sessions/{id}/generations` | Queue one immutable snapshot; returns HTTP 202 |
| `GET /generations/{id}` | Poll status, error or result |
| `GET /generations/{id}/image` | Download verified PNG |
| `GET /generations/{id}/thumbnail` | Download verified JPEG thumbnail |
| `POST /sessions/{id}/finish` | Recheck the saved result before allowing reset |
| `GET /admin/archive` | Staff search by reference/date/theme/style/innovation |
| `GET /admin/export` | ZIP with images, manifests, JSON and CSV indexes |

Sample answer update (the revision starts at zero):

```json
{
  "revision": 0,
  "answers": {
    "use": "football",
    "capacity": "60000",
    "setting": "desert",
    "theme": "qatar",
    "style": "qatari",
    "shape": "oval",
    "roof": "solar",
    "materials": ["stone", "perforated_metal"],
    "palette": "ivory",
    "experience": "comfort",
    "innovation": "gardens",
    "technologies": ["ai_guidance", "digital_twin"],
    "environment": ["solar", "water", "passive"],
    "legacy": "community",
    "signature": {"mode": "surprise"}
  }
}
```

PATCH allows a subset of answers. Set an answer to `null` to remove it. Successful
updates increment `revision`; stale updates get HTTP 409. Option IDs, not translated
display labels, must be submitted. Multiple-choice answers currently require at
least one selection; the brief says “up to”, so confirm whether zero should be
allowed. Limits are 2 materials, 2 technologies and 3 environmental strategies.

After showing any review notes and receiving visitor confirmation, submit:

```json
{
  "request_id": "b8052047-4f4c-422a-a996-a366f5c24629",
  "revision": 1,
  "accepted_notes": []
}
```

Create a UUID for each **intentional** generation. Reuse the same UUID/body when
retrying a submission after a network error; it returns the original job rather
than generating twice. A failed job is not restarted by resending its request ID.
After reviewing a failed attempt, submit a new ID to deliberately try again.

Keep the returned session/job IDs in frontend storage so a browser refresh can
resume the session. Poll roughly every 1–2 seconds and stop on a terminal status.
Only show the final reveal when status is `completed`. A job's choices are frozen;
edits are blocked while it is active. Later edits create a new revision and leave
existing archives unchanged.

Statuses: `queued` → `generating` → `saving` → `completed`.
Terminal failures: `failed` or `interrupted`. The queue is persistent and bounded.
Jobs interrupted during a cloud request are **not automatically resubmitted**.
If all archive files were written before an interruption, startup can verify and
complete the job without generating another image.

`finish` returns `can_reset: true` only after checking the latest completed result.
Reset the visitor UI by starting a new session; never delete archived data. Draft
abandonment and timed UI reset will be implemented in the frontend.

Archive search and export share `reference`, `theme`, `style`, `innovation`,
`date_from` and `date_to` filters. Dates are inclusive UTC calendar dates. Use
`limit` and `offset` to page; each export includes at most 100 designs. UTC is
stored to avoid ambiguity; the frontend can display museum-local time.

## Archive and backups

```text
data/
  stadium.sqlite3          # Sessions, frozen jobs and archive metadata
  archive/<job-uuid>/
    image.png              # Full provider resolution, normalised to RGB PNG
    thumbnail.jpg
    manifest.json          # Choices, story, prompts, seeds, versions and attempts
```

Files are atomically replaced, flushed and hash-verified before a job is marked
completed. The manifest records the actual output dimensions. This prototype does
not upscale images or guarantee 4K. The recorded seed drives prompt variations;
it is not a provider-level reproducibility guarantee.

Stop the server with Ctrl+C, allowing an active job to finish. Then create a backup
outside the data directory (prefer an external drive for an actual backup):

```sh
.venv/bin/python scripts/backup.py ./data ./backups/demo-001
```

Restore into a **new** directory, verify it, and point `DATA_DIR` to that directory:

```sh
.venv/bin/python scripts/backup.py ./backups/demo-001 ./restored-data
```

The backup tool locks out concurrent app operation, uses SQLite's backup API,
checks database integrity, and verifies completed image hashes and metadata.
Existing destinations are never overwritten. API keys and `.env` are not copied.
An image export is useful for museum reuse; the directory snapshot is the full
application-data recovery mechanism.

## Tests

```sh
.venv/bin/python -m pytest -q
```

The suite covers full mock generation, selection validation, revisions,
compatibility confirmation, duplicate submissions/images, archive corruption,
restart recovery, backup/restore, low storage, authentication, provider request
formats and sanitised failures. Provider fixtures are not live acceptance tests.

## Scope and next steps

Implemented: questionnaire data and validation; saved anonymous drafts; review;
OpenAI/Google adapters; labelled test provider; persistent single-worker generation;
deterministic title/story templates; saved prompts and variation records; verified
archive files; staff search/export; backup/restore; OpenAPI contract and tests.

Not yet implemented or accepted:

- Frontend and illustrated option cards; bilingual museum-approved copy. The API
  currently accepts English only rather than silently returning English for Arabic.
- Real offline AI/procedural rendering and hardware benchmarks. Mock images do not
  fulfil the client's offline-generation requirement.
- Public free-text moderation. `ALLOW_FREE_TEXT=false` by default; enabling it is
  for controlled developer testing only. Length/control-character checks and prompt
  delimiting alone do not constitute suitable museum moderation.
- Comprehensive architectural compatibility and visual answer-adherence checks.
  Initial rules cover open roofs with solar/shade priorities and athletics proximity.
- Perceptual/semantic duplicate detection. Current duplicate checks compare exact
  decoded pixels; different-looking architecture is not guaranteed by this check.
- Staff UI, two-station synchronisation, unattended backups/alerts, archive indexing
  at exhibition scale, OS auto-start, retention policy and full deployment hardening.
- 4K acceptance, provider latency/cost evaluation, content rights/licence review,
  museum training and the additional requirements in the referenced technical tender.

Measured Mac results and limitations: [Benchmark report](docs/benchmark-results.md).
