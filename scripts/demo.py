"""Run one complete session against a running backend. Cloud mode can incur API usage."""
import argparse
import json
import os
import time
from uuid import uuid4

import httpx

ANSWERS = {
    "use": "football", "capacity": "60000", "setting": "desert", "theme": "qatar", "style": "qatari",
    "shape": "oval", "roof": "solar", "materials": ["stone", "perforated_metal"], "palette": "ivory",
    "experience": "comfort", "innovation": "gardens", "technologies": ["ai_guidance", "digital_twin"],
    "environment": ["solar", "water", "passive"], "legacy": "community", "signature": {"mode": "surprise"},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--allow-paid", action="store_true", help="Permit one cloud generation (and configured duplicate retry)")
    args = parser.parse_args()
    headers = {"Authorization": f"Bearer {os.environ['KIOSK_API_KEY']}"} if os.getenv("KIOSK_API_KEY") else {}
    with httpx.Client(base_url=args.url, headers=headers, timeout=30) as c:
        def call(method, path, **kwargs):
            r = c.request(method, path, **kwargs)
            r.raise_for_status()
            return r.json()
        health = call("GET", "/health")
        if health["provider"] in {"openai", "gemini"} and not args.allow_paid:
            parser.error("Cloud generation is configured. Add --allow-paid to run a billable demo.")
        session = call("POST", "/api/v1/sessions", json={"language": "en"})
        sid = session["id"]
        updated = call("PATCH", f"/api/v1/sessions/{sid}/answers", json={"revision": 0, "answers": ANSWERS})
        review = call("GET", f"/api/v1/sessions/{sid}/review")
        job = call("POST", f"/api/v1/sessions/{sid}/generations", json={
            "revision": updated["revision"], "request_id": str(uuid4()),
            "accepted_notes": [n["code"] for n in review["notes_to_confirm"]]})
        print(f"Generation {job['id']} ({health['provider']})", flush=True)
        deadline = time.monotonic() + 600
        while job["status"] in {"queued", "generating", "saving"}:
            if time.monotonic() > deadline:
                raise SystemExit("Stopped polling. Job is preserved; fetch its status before submitting another.")
            time.sleep(2)
            job = call("GET", f"/api/v1/generations/{job['id']}")
        print(json.dumps(job, indent=2, ensure_ascii=False))
        if job["status"] != "completed":
            raise SystemExit(1)
        print("Image:", args.url + job["result"]["image_url"])
        print("Finish:", call("POST", f"/api/v1/sessions/{sid}/finish"))


if __name__ == "__main__":
    main()
