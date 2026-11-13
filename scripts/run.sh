#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f .env ]; then
    cp .env.example .env
fi

stop_mps() {
    pid=""
    if command -v lsof >/dev/null 2>&1; then
        pid="$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
        if [ -n "$pid" ]; then
            command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
            case "$command_line" in
                *uvicorn*app.main:app*) ;;
                *)
                    printf 'Port 8000 is used by another app; stop it before changing modes.\n' >&2
                    exit 1
                    ;;
            esac
        fi
    fi

    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        case "$command_line" in
            *uvicorn*app.main:app*) ;;
            *)
                printf 'Recorded MPS PID is no longer the app process; leaving it untouched.\n' >&2
                pid=""
                ;;
        esac
    fi

    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        attempt=0
        while kill -0 "$pid" 2>/dev/null && [ "$attempt" -lt 10 ]; do
            sleep 1
            attempt=$((attempt + 1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            printf 'The server is finishing its current generation. Wait for it to stop, then retry.\n' >&2
            exit 1
        fi
    fi
}

run_docker_cpu() {
    stop_mps
    GENERATION_PROVIDER=local docker compose -f compose.dev.yaml up --build -d
    printf '\nDocker CPU mode is running at http://localhost:3000/\n'
}

run_mps() {
    if [ "$(uname -s)" != "Darwin" ]; then
        printf 'MPS mode requires macOS with Apple Silicon.\n' >&2
        exit 1
    fi
    if [ ! -x .venv/bin/python ]; then
        printf 'Create .venv and install backend/requirements.lock.txt, then run scripts/setup_flux.sh.\n' >&2
        exit 1
    fi
    if ! .venv/bin/python -c 'from app.core.config import Settings; from app.providers.flux import mlx_ready; raise SystemExit(0 if mlx_ready(Settings.from_env()) else 1)'; then
        printf 'FLUX 3 Klein needs initial setup. Run ./scripts/setup_flux.sh first.\n' >&2
        exit 1
    fi

    stop_mps
    # Stop the Docker UI/API stack if it is running; preserve its data volume.
    if docker info >/dev/null 2>&1; then
        docker compose -f compose.dev.yaml down
    fi
    if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
        printf 'Port 8000 is already in use. Stop that server, then select MPS again.\n' >&2
        exit 1
    fi

    printf 'Starting FLUX 3 Klein (MLX/Metal) at http://127.0.0.1:8000/. Press Ctrl+C to stop.\n'
    exec env GENERATION_PROVIDER=local LOCAL_IMAGE_ENGINE=flux3 LOCAL_IMAGE_DEVICE=mps LOCAL_IMAGE_LOCAL_FILES_ONLY=true \
        .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
}

run_api() {
    provider="$1"
    stop_mps
    case "$provider" in
        openai) key_name=OPENAI_API_KEY ;;
        gemini) key_name=GEMINI_API_KEY ;;
        *)
            printf 'Choose openai or gemini for API mode.\n' >&2
            exit 1
            ;;
    esac

    if ! grep -Eq "^${key_name}=.+$" .env; then
        printf '%s is empty in .env. Add your key there, then run this option again.\n' "$key_name" >&2
        exit 1
    fi

    COMPOSE_FILE=compose.dev.yaml GENERATION_PROVIDER="$provider" docker compose -f compose.dev.yaml up --build -d
    printf '\n%s API mode is running at http://localhost:3000/\n' "$provider"
}

run_stop() {
    stop_mps
    if docker info >/dev/null 2>&1; then
        docker compose -f compose.dev.yaml down
    fi
    printf 'Stadium app stopped. Data volumes were preserved.\n'
}

mode="${1:-}"
if [ -z "$mode" ]; then
    printf 'Choose image generation mode:\n'
    printf '  1) Docker local model (CPU)\n'
    printf '  2) Mac FLUX 3 Klein (Metal, faster)\n'
    printf '  3) API key (OpenAI or Gemini)\n'
    printf '  4) Stop the app\n'
    printf 'Selection: '
    read -r mode
fi

case "$mode" in
    1|docker)
        run_docker_cpu
        ;;
    2|mps)
        run_mps
        ;;
    3|api)
        provider="${2:-}"
        if [ -z "$provider" ]; then
            printf 'API provider (openai/gemini): '
            read -r provider
        fi
        run_api "$provider"
        ;;
    4|stop)
        run_stop
        ;;
    openai|gemini)
        run_api "$mode"
        ;;
    *)
        printf 'Choose 1, 2, or 3.\n' >&2
        exit 2
        ;;
esac
