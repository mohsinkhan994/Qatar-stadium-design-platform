import asyncio
import json
import logging
import secrets
import shutil

from .design import build_design
from .providers import ProviderError
from .storage import now, prepare_image, save_archive

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, db, settings, provider):
        self.db, self.settings, self.provider = db, settings, provider
        self.stopping = asyncio.Event()

    def process(self, job):
        job_id = job["id"]
        payload = json.loads(job["payload"])
        try:
            if shutil.disk_usage(self.settings.data_dir).free < self.settings.min_free_disk_mb * 1024 * 1024:
                raise ProviderError("low_storage", "Insufficient local storage. Ask staff to free space before generating.")
            if payload["provider"] != self.provider.name or payload["model"] != self.provider.model:
                raise ProviderError("configuration_changed", "Generation configuration changed since this job was queued. Review and submit a new job.")
            for attempt in range(self.settings.max_attempts):
                if attempt:
                    payload["design"] = build_design(payload["answers"], secrets.randbits(32))
                payload["attempts"].append({"started_at": now(), "seed": payload["design"]["variation"]["seed"],
                                            "prompt": (payload["design"].get("flux_prompt", payload["design"]["prompt"])
                                                       if self.settings.provider == "local" and self.settings.local_engine == "flux3"
                                                       else payload["design"]["prompt"])})
                self.db.update_job(job_id, "generating", payload)
                result = self.provider.generate(payload["design"])
                full, thumb, info = prepare_image(result.image)
                payload["attempts"][-1]["generation"] = result.metadata
                payload["attempts"][-1]["pixel_sha256"] = info["pixel_sha256"]
                if self.db.image_exists(info["pixel_sha256"]):
                    payload["attempts"][-1]["outcome"] = "duplicate"
                    self.db.update_job(job_id, "generating", payload)
                    continue
                payload["attempts"][-1]["outcome"] = "accepted"
                payload.update(image=info, generation=result.metadata, completed_at=now())
                self.db.update_job(job_id, "saving", payload)
                save_archive(self.settings.data_dir, job_id, payload, full, thumb)
                self.db.update_job(job_id, "completed", payload)
                return
            raise ProviderError("duplicate_output", "Repeated image detected. No result was archived; review and try a new variation.")
        except ProviderError as exc:
            self.db.update_job(job_id, "failed", payload, exc.code, exc.message)
        except Exception:
            # Never expose provider response bodies, user prompts or API keys in errors.
            log.error("Job %s failed during image validation or archive storage", job_id)
            self.db.update_job(job_id, "failed", payload, "processing_failed",
                               "Image validation or saving failed. Answers were preserved; staff should check storage and provider configuration.")

    async def run(self):
        while not self.stopping.is_set():
            job = await asyncio.to_thread(self.db.claim)
            if job:
                await asyncio.to_thread(self.process, job)
            else:
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=0.2)
                except TimeoutError:
                    pass
