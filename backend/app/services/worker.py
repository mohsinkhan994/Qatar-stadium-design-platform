import asyncio
import json
import logging
import secrets
import shutil
import time
from .validation import evaluate_image

from app.domain.design import build_design
from app.providers import ProviderError
from app.repositories.storage import now, prepare_image, save_archive

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, db, settings, provider, evaluator=None):
        self.db, self.settings, self.provider = db, settings, provider
        from .validation import LocalCommandEvaluator

        self.evaluator = evaluator or (
            LocalCommandEvaluator(
                list(settings.evaluator_command), min(30, settings.timeout)
            )
            if settings.evaluator_command
            else None
        )
        self.stopping = asyncio.Event()

    def process(self, job):
        job_id = job["id"]
        payload = json.loads(job["payload"])
        started = time.monotonic()
        attempt_started = started
        correction = []
        try:
            if (
                shutil.disk_usage(self.settings.data_dir).free
                < self.settings.min_free_disk_mb * 1024 * 1024
            ):
                raise ProviderError(
                    "low_storage",
                    "Insufficient local storage. Ask staff to free space before generating.",
                )
            if (
                payload["provider"] != self.provider.name
                or payload["model"] != self.provider.model
            ):
                raise ProviderError(
                    "configuration_changed",
                    "Generation configuration changed since this job was queued. Review and submit a new job.",
                )
            for attempt in range(self.settings.max_attempts):
                if attempt:
                    if time.monotonic() - started >= self.settings.timeout:
                        raise ProviderError(
                            "generation_deadline", "Generation time budget exhausted."
                        )
                    self.db.update_job(job_id, "retrying", payload)
                    original_signature = payload["design"]["signature"]
                    retry_answers = {
                        **payload["answers"],
                        "signature": {"mode": "text", "text": original_signature},
                    }
                    payload["design"] = build_design(
                        retry_answers, secrets.randbits(32)
                    )
                    if correction:
                        import json as json_data

                        for key in ("prompt", "flux_prompt"):
                            payload["design"][key] += (
                                "\nCorrect these observed omissions while preserving all choices: "
                                + json_data.dumps(correction)
                            )
                from app.domain.references import select_reference

                reference = (
                    select_reference(
                        self.settings.reference_manifest,
                        payload["answers"],
                        payload["design"]["variation"]["seed"],
                    )
                    if self.settings.provider == "local"
                    and self.settings.local_engine == "flux3"
                    else None
                )
                if reference:
                    payload["design"]["reference"] = reference
                    for key in ("prompt", "flux_prompt"):
                        payload["design"][key] = (
                            "Use the supplied reference only for compatible field geometry and composition. "
                            "Apply the visitor-selected architecture, roof and materials from the following caption. "
                            "The caption's P0 constraints take precedence over conflicting reference details.\n"
                            + payload["design"][key]
                        )
                attempt_started = time.monotonic()
                payload["attempts"].append(
                    {
                        "started_at": now(),
                        "seed": payload["design"]["variation"]["seed"],
                        "prompt": (
                            payload["design"].get(
                                "flux_prompt", payload["design"]["prompt"]
                            )
                            if self.settings.provider == "local"
                            and self.settings.local_engine == "flux3"
                            else payload["design"]["prompt"]
                        ),
                    }
                )
                self.db.update_job(job_id, "generating", payload)
                bounded_generate = getattr(self.provider, "generate_with_timeout", None)
                remaining = max(
                    0.001, self.settings.timeout - (time.monotonic() - started)
                )
                result = (
                    bounded_generate(payload["design"], remaining)
                    if bounded_generate
                    else self.provider.generate(payload["design"])
                )
                payload["attempts"][-1]["duration_seconds"] = round(
                    time.monotonic() - attempt_started, 3
                )
                full, thumb, info = prepare_image(result.image)
                payload["attempts"][-1]["generation"] = result.metadata
                payload["attempts"][-1]["pixel_sha256"] = info["pixel_sha256"]
                from app.repositories.storage import atomic_write

                candidate = (
                    self.settings.data_dir
                    / "candidates"
                    / job_id
                    / f"{attempt + 1}.png"
                )
                atomic_write(candidate, full)
                payload["attempts"][-1]["candidate"] = str(
                    candidate.relative_to(self.settings.data_dir)
                )
                if self.db.image_exists(
                    info["pixel_sha256"]
                ) or self.db.similar_image_exists(
                    info.get("dhash"), self.settings.perceptual_duplicate_distance
                ):
                    payload["attempts"][-1]["outcome"] = "duplicate"
                    self.db.update_job(job_id, "generating", payload)
                    continue
                self.db.update_job(job_id, "validating", payload)
                remaining = self.settings.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise ProviderError(
                        "generation_deadline", "Generation time budget exhausted."
                    )
                evaluation = evaluate_image(
                    self.evaluator,
                    full,
                    payload["design"],
                    self.settings.validation_threshold,
                    timeout=remaining,
                )
                payload["attempts"][-1]["validation"] = evaluation
                payload["validation"] = evaluation
                if evaluation["status"] == "failed":
                    payload["attempts"][-1]["outcome"] = "validation_failed"
                    correction = evaluation.get("missing_features", []) or [
                        "Re-establish every P0 field, roof, shape and signature constraint explicitly."
                    ]
                    if (
                        evaluation["recommend_regeneration"]
                        and self.settings.provider == "local"
                        and attempt + 1 < self.settings.max_attempts
                    ):
                        continue
                    raise ProviderError(
                        "visual_validation_failed",
                        "The image did not meet the selected design requirements. Review and try again.",
                    )
                payload["duration_seconds"] = round(time.monotonic() - started, 3)
                if (
                    self.settings.provider == "local"
                    and time.monotonic() - started > self.settings.timeout
                ):
                    raise ProviderError(
                        "generation_deadline",
                        "Generation time budget exhausted; the candidate was retained for staff review.",
                    )
                payload["attempts"][-1]["outcome"] = "accepted"
                payload.update(
                    image=info, generation=result.metadata, completed_at=now()
                )
                self.db.update_job(job_id, "saving", payload)
                save_archive(self.settings.data_dir, job_id, payload, full, thumb)
                self.db.update_job(job_id, "completed", payload)
                return
            raise ProviderError(
                "duplicate_output",
                "Repeated image detected. No result was archived; review and try a new variation.",
            )
        except ProviderError as exc:
            payload["duration_seconds"] = round(time.monotonic() - started, 3)
            if payload["attempts"]:
                last = payload["attempts"][-1]
                last.setdefault(
                    "duration_seconds", round(time.monotonic() - attempt_started, 3)
                )
                last.setdefault("outcome", "failed")
                last["error_code"] = exc.code
            self.db.update_job(job_id, "failed", payload, exc.code, exc.message)
        except Exception:
            payload["duration_seconds"] = round(time.monotonic() - started, 3)
            if payload["attempts"]:
                payload["attempts"][-1].setdefault(
                    "duration_seconds", round(time.monotonic() - attempt_started, 3)
                )
                payload["attempts"][-1].setdefault("outcome", "processing_failed")
            # Never expose provider response bodies, user prompts or API keys in errors.
            log.error(
                "Job %s failed during image validation or archive storage", job_id
            )
            self.db.update_job(
                job_id,
                "failed",
                payload,
                "processing_failed",
                "Image validation or saving failed. Answers were preserved; staff should check storage and provider configuration.",
            )

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
