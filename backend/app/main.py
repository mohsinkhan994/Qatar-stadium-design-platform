"""FastAPI application composition and process lifecycle."""
import asyncio
import fcntl
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.core.config import ROOT, Settings
from app.providers import provider_for
from app.repositories.storage import Database, recover
from app.services.worker import Worker
from app.api.routes import admin, generations, health, questionnaire, sessions


def create_app(settings=None, provider=None):
    settings = settings or Settings.from_env()
    settings.validate()

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        # One local worker owns each database. Prevent duplicate billing from multiple processes.
        lock = (settings.data_dir / "worker.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError("This data directory already has a running backend. Use exactly one uvicorn worker.")
        try:
            app.state.db = Database(settings.data_dir)
            app.state.provider = provider or provider_for(settings)
            recover(app.state.db)
            worker = Worker(app.state.db, settings, app.state.provider)
            task = asyncio.create_task(worker.run())
            try:
                yield
            finally:
                worker.stopping.set()
                await task
                close = getattr(app.state.provider, "close", None)
                if close:
                    await asyncio.to_thread(close)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    app = FastAPI(title="Stadium Design API", version=__version__, lifespan=lifespan,
                  description="Mock output is a labelled fixture. Local image generation uses CPU, CUDA or Apple MPS, depending on configuration.")
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "backend", "testserver"])
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type", "X-Admin-Key"])

    for module in (health, questionnaire, sessions, generations, admin):
        app.include_router(module.router)

    frontend = ROOT / "frontend"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
