"""Repeatable local inference matrix. No cloud requests; dry-run is the default."""

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.domain.catalog import QUESTIONS
from app.domain.design import build_design, validate_answers
from app.core.config import Settings
from app.providers.flux import Flux3Provider


def cases(count=50):
    rng = random.Random(20261113)
    result = []
    for i in range(count):
        answers = {
            q["id"]: (
                [
                    o["id"]
                    for o in rng.sample(
                        q["options"], rng.randint(1, q["max_selections"])
                    )
                ]
                if q["type"] == "multiple"
                else rng.choice(q["options"])["id"]
            )
            for q in QUESTIONS
            if q["id"] != "signature"
        }
        answers["signature"] = {"mode": "surprise"}
        if i == 0:
            answers.update(
                use="athletics", capacity="20000", setting="mountains", roof="open"
            )
        if i == 1:
            answers.update(
                use="football",
                capacity="80000_plus",
                style="futuristic",
                roof="retractable",
            )
        if i == 2:
            answers.update(
                setting="sea",
                theme="waves",
                signature={"mode": "text", "text": "A sculptural waterfront promenade"},
            )
        if i == 3:
            answers.update(
                theme="nature",
                innovation="moving_facade",
                signature={"mode": "text", "text": "A branching-tree entrance"},
            )
        if i == 4:
            answers.update(
                setting="desert",
                roof="solar",
                environment=["passive", "solar", "water"],
            )
        result.append(
            {
                "id": f"case-{i + 1:02}",
                "seed": 1000 + i,
                "answers": validate_answers(
                    answers, complete=True, allow_free_text=True
                ),
            }
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Exercise the shared worker, archive and optional evaluator",
    )
    parser.add_argument(
        "--prompt-set",
        type=Path,
        help="JSON list of baseline id/prompt/seed/answers records",
    )
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--output", type=Path, default=Path("output/benchmarks/balanced")
    )
    parser.add_argument(
        "--profile",
        choices=["fast_preview", "balanced", "high_quality"],
        default="balanced",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("limit must be 1..50")
    args.output.mkdir(parents=True, exist_ok=True)
    matrix = cases()
    (args.output / "cases.json").write_text(json.dumps(matrix, indent=2))
    settings = Settings.from_env()
    settings.provider = "local"
    settings.local_engine = "flux3"
    settings.inference_profile = args.profile
    settings.timeout = max(settings.timeout, 600)
    settings.data_dir = args.output / "runtime"
    settings.validate()
    provider = Flux3Provider(settings) if args.run else None
    baseline = (
        {row["id"]: row for row in json.loads(args.prompt_set.read_text())}
        if args.prompt_set
        else {}
    )
    records = []
    if args.pipeline and provider:
        from app.repositories.storage import Database
        from app.services.worker import Worker

        database = Database(settings.data_dir)
        worker = Worker(database, settings, provider)
    try:
        for case in matrix[: args.limit]:
            design = build_design(case["answers"], case["seed"])
            if baseline:
                previous = baseline[case["id"]]
                if (
                    previous["answers"] != case["answers"]
                    or previous["seed"] != case["seed"]
                ):
                    raise ValueError("Baseline inputs do not match benchmark case")
                design["prompt"] = design["flux_prompt"] = previous["prompt"]
                design["prompt_version"] = previous["prompt_version"]
            start = time.monotonic()
            record = {
                **case,
                "prompt": design["flux_prompt"],
                "prompt_version": design["prompt_version"],
                "profile": args.profile,
                "validation": {"status": "unavailable"},
                "status": "dry_run",
            }
            if provider:
                try:
                    if args.pipeline:
                        from uuid import uuid4
                        from app.repositories.storage import now, encode

                        job_id, session_id = str(uuid4()), str(uuid4())
                        payload = {
                            "archive_reference": job_id,
                            "session_id": session_id,
                            "answers": case["answers"],
                            "design": design,
                            "provider": "local",
                            "model": provider.model,
                            "attempts": [],
                            "created_at": now(),
                            "station": "benchmark",
                            "language": "en",
                        }
                        with database.connect() as conn:
                            conn.execute(
                                "INSERT INTO sessions(id,language,station,created_at,updated_at) VALUES (?,?,?,?,?)",
                                (session_id, "en", "benchmark", now(), now()),
                            )
                            conn.execute(
                                "INSERT INTO jobs(id,session_id,request_id,fingerprint,status,created_at,updated_at,payload) VALUES (?,?,?,?,?,?,?,?)",
                                (
                                    job_id,
                                    session_id,
                                    job_id,
                                    "benchmark",
                                    "queued",
                                    now(),
                                    now(),
                                    encode(payload),
                                ),
                            )
                        worker.process(database.job(job_id))
                        row = database.job(job_id)
                        outcome = json.loads(row["payload"])
                        record.update(
                            status="generated"
                            if row["status"] == "completed"
                            else "error",
                            job_status=row["status"],
                            error=row["error_code"],
                            attempts=outcome["attempts"],
                            validation=outcome.get(
                                "validation", {"status": "unavailable"}
                            ),
                            metadata=outcome.get("generation", {}),
                            latency_seconds=time.monotonic() - start,
                        )
                        if row["status"] == "completed":
                            (args.output / (case["id"] + ".png")).write_bytes(
                                (
                                    settings.data_dir / "archive" / job_id / "image.png"
                                ).read_bytes()
                            )
                    else:
                        image = provider.generate(design)
                        (args.output / (case["id"] + ".png")).write_bytes(image.image)
                        record.update(
                            status="generated",
                            metadata=image.metadata,
                            latency_seconds=time.monotonic() - start,
                        )
                except Exception as exc:
                    record.update(
                        status="error",
                        error=type(exc).__name__,
                        latency_seconds=time.monotonic() - start,
                    )
            records.append(record)
            (args.output / "results.json").write_text(json.dumps(records, indent=2))
            print(
                case["id"],
                record["status"],
                round(record.get("latency_seconds", 0), 2),
                flush=True,
            )
    finally:
        if provider:
            provider.close()
    times = [r["latency_seconds"] for r in records if r["status"] == "generated"]
    summary = {
        "backend": ("mlx" if provider.uses_mlx else "diffusers")
        if provider
        else "not_run",
        "profile": args.profile,
        "cases": len(records),
        "generated": len(times),
        "errors": sum(r["status"] == "error" for r in records),
        "mean_latency_seconds": statistics.mean(times) if times else None,
        "visual_quality_score": None,
        "critical_failure_rate": None,
        "first_attempt_acceptance_rate": None,
        "regeneration_frequency": None,
        "note": "Direct-provider benchmark; visual assessment and worker regeneration metrics require a configured real evaluator and pipeline benchmark.",
    }
    assessed = [
        r for r in records if r.get("validation", {}).get("overall_score") is not None
    ]
    if assessed:
        summary["visual_quality_score"] = statistics.mean(
            r["validation"]["overall_score"] for r in assessed
        )
        summary["critical_failure_rate"] = sum(
            not r["validation"]["critical_constraints_passed"] for r in assessed
        ) / len(assessed)
        summary["first_attempt_acceptance_rate"] = sum(
            bool(r.get("attempts"))
            and r["attempts"][0].get("validation", {}).get("status") == "passed"
            for r in assessed
        ) / len(assessed)
    if args.pipeline and provider:
        summary["regeneration_frequency"] = sum(
            len(r.get("attempts", [])) > 1 for r in records
        ) / len(records)
        summary["note"] = (
            "Shared worker benchmark; visual metrics remain null unless a real image evaluator returned assessments."
        )
    peaks = [r.get("metadata", {}).get("peak_memory_bytes") for r in records]
    summary["peak_device_memory_bytes"] = max(
        (v for v in peaks if v is not None), default=None
    )
    summary["warm_mean_latency_seconds"] = (
        statistics.mean(
            [
                r["latency_seconds"]
                for r in records
                if r["status"] == "generated"
                and r.get("metadata", {}).get("cold_start") is False
            ]
        )
        if any(
            r["status"] == "generated"
            and r.get("metadata", {}).get("cold_start") is False
            for r in records
        )
        else None
    )
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
