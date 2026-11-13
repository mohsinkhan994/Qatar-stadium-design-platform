# Stadium generation quality pipeline

## Architecture and responsibilities

The existing FastAPI app, SQLite queue and archive remain in place. The following
modules extend that pipeline:

- `app/domain/architecture.py`: explicit mappings for every approved option,
  P0/P1/P2 constraint records, five architectural caption sections and compatible
  seeded composition/massing variations.
- `app/domain/design.py`: input validation, compatibility confirmations, resolved
  signature, visitor-facing description and the versioned design record.
- `app/providers/flux.py`: common `generate(design)` interface, serial inference,
  persistent Diffusers components and backend metadata.
- `app/providers/mlx_session.py` and `scripts/flux_mlx.py`: persistent JSON-line
  child process that isolates MLX dependencies, keeps weights resident, enforces
  a response deadline, and reaps failed children. No listening network service.
- `app/providers/profiles.py`: conservative resolution profiles.
- `app/services/validation.py`: pixel-evaluator contract and local command bridge.
- `app/services/worker.py`: validation, bounded critical retries, candidate
  retention and archive commit. Blocking inference stays in `asyncio.to_thread`.
- `app/domain/references.py`: local, curated, provenance-bearing reference assets.

The questionnaire IDs and options have not changed. Both GPU backends receive
exactly the same architectural caption. Constraints are prompt intent, not proof
that the generated pixels comply. Capacity is a scale cue, not a seat-count claim.

## Verified runtime capabilities

Inspection on 13 November 2026 found MFLUX 0.24.0 / MLX 0.32.4 and Diffusers 0.43.0
with PyTorch 2.15.0 and Transformers 5.22.2. The configured model is FLUX 3 Image
Klein, a distilled 5.6B image transformer with a separate Qwen3-VL-4B text encoder.
The checkpoint's documented baseline is 16 steps without guidance. The Mac Q4
conversion quantizes the transformer, text encoder and autoencoder; weight size
is not equivalent to peak inference memory.

Installed MFLUX uses `Flux3FlowMapScheduler`; its distilled sampling resolver
ignores guidance. Its prompt encoder supports up to 4096 tokens. No FLUX.1/2
negative-prompt, strength or scheduler parameters were added. CUDA preserves the
checkpoint's modular pipeline and uses BF16 components with an FP32 VAE; a CUDA
GPU without BF16 support is rejected explicitly. MPS uses native MLX/Metal, not
a Docker GPU device. Diffusers CUDA remains hardware-unverified on this Mac.

The official model guidance asks for full scene caption expansion. The application
supplies a deterministic questionnaire-expanded caption and continues to omit the
additional prompt-upsampler model. This is not an LLM upsampler, and equivalence
to the vendor's recommended upsampler has not been established. Compare them on
representative scenes before claiming optimal quality.

Sources:
- https://huggingface.co/black-forest-labs/flux-3-image-klein
- https://huggingface.co/mflux-community/flux-3-image-klein-mflux-q4
- Installed `mflux/models/flux3/variants/flux3_klein_core.py`
- Installed `mflux/models/flux3/variants/edit/flux3_klein_edit.py`
- Installed `diffusers/modular_pipelines/flux3/encoders.py`

## Profiles and operation

`INFERENCE_PROFILE` accepts:

| Profile | Resolution | Steps | Use |
| --- | --- | --- | --- |
| `fast_preview` | 768 x 512 | 16 | Opt-in lower-resolution trial |
| `balanced` | Existing `LOCAL_IMAGE_WIDTH` / `HEIGHT` | Existing `LOCAL_IMAGE_STEPS`, default 16 | Preserved default |
| `high_quality` | 1344 x 768 | 16 | Opt-in larger output; the name does not guarantee better adherence |

No guidance increase or checkpoint substitution is performed. Run one backend
process with one serial worker per archive. CUDA model loading is reused; the
MLX child reuses the same model until shutdown, timeout or a switch between text
and reference modes. Normal shutdown closes stdin and waits, then terminates
and kills only if needed. An executing CUDA kernel cannot be forcibly interrupted
safely by this thread-based adapter: its deadline is checked at pipeline boundaries.
MLX can be hard-stopped by terminating its isolated child.

`POST /api/v1/generations/{id}/cancel` cancels queued work atomically. Active jobs
return HTTP 409. Existing request idempotency and the SQLite unique active-job
index also cover `validating` and `retrying`. Visitor copy describes checking and
refining, without showing model names, internal prompts or artificial percentages.

## Real image evaluation

No suitable standalone vision evaluator is configured in this checkout. The FLUX
text encoder is not treated as an image-scoring service. With no evaluator, stored
validation is `status: unavailable`, with null score and null critical pass flag.
Image integrity checks and exact-hash checks are separate from visual adherence.

An operator can configure an existing **local** vision program:

```dotenv
VISUAL_EVALUATOR_COMMAND=["/absolute/path/to/python", "/absolute/path/to/evaluate.py"]
VISUAL_VALIDATION_THRESHOLD=85
```

The command receives JSON on stdin with `image_path` (actual candidate PNG),
`constraints`, `signature` and criterion weights. It must inspect that image and
emit one JSON object on stdout. It must keep diagnostic logs on stderr. Return:

- `criteria`: numeric 0..100 values for `stadium_purpose`, `shape_and_roof`,
  `location_and_style`, `signature_feature`, `materials`, `landscaping`.
- `critical_constraints_passed`: an explicit boolean assessing playing geometry,
  roof, exterior shape, signature and major contradictions independently.
- `missing_features`: short observations grounded in the image, not new choices.

Weights are 25, 20, 20, 15, 10 and 10 percent respectively. Scores are calculated
locally from the returned criteria, not trusted from a provider's overall score.
Non-finite, missing or out-of-range results fail evaluation. Invisible operational
features and sustainability performance must not be counted as visual failures.
The evaluator command has a bounded timeout. No paid evaluator is added.

Local critical failures may receive one revised candidate by default, with a new
seed and the same resolved signature. Low overall score alone does not trigger an
aesthetic retry. The first candidate meeting both acceptance gates is archived;
an invalid result is never promoted just because it is the highest-scoring one.
This is early acceptance, not an unconditional two-image tournament. API visual
failures do not trigger automatic paid regeneration. Exact-duplicate retries retain
the existing behavior, subject to the configured attempt cap.

`MAX_GENERATION_ATTEMPTS` defaults to two in the templates. Existing private env
files are not overwritten and can still set one. The total local job budget uses
`GENERATION_TIMEOUT_SECONDS`; remaining time is passed to the MLX adapter and local evaluator command. Custom
in-process evaluators must enforce their own timeout; the supplied command bridge
enforces a subprocess timeout.

## Reference guidance

Reference mode is off unless `REFERENCE_MANIFEST` points to a JSON array. Each
entry needs `category`, `file`, `source` and `license`. Paths resolve inside the
manifest directory, with image size and integrity checks. Do not use unlicensed
third-party architecture images. Shape-only entries also require `compatible_uses`
to prevent, for example, a football reference replacing an athletics track.

```json
[
  {
    "category": "athletics",
    "file": "owned-track-reference.png",
    "source": "Internal project asset; record creator and date",
    "license": "Project-owned; approved for this use"
  },
  {
    "category": "circular",
    "file": "owned-circular-football.png",
    "source": "Internal project asset; record creator and date",
    "license": "Project-owned; approved for this use",
    "compatible_uses": ["football", "community"]
  }
]
```

Supported categories: athletics, football, multi_sport, circular, oval,
rectangular, sculptural. Purpose references take priority over shape references;
seeded selection varies within a matching category. No matching entry means normal
text-only generation. Invalid configured assets fail explicitly rather than being
silently ignored. No stock reference library is bundled or downloaded.

MFLUX uses `Flux3KleinEdit.generate_image(image_paths=[...])`; Diffusers receives
`image` as a decoded PIL image. Each adapter follows its installed API. Reference
conditioning can affect style and geometry and needs visual acceptance testing.
A provenance string records the operator's assertion; it does not verify rights.
For Docker, mount the curated asset directory read-only and set the manifest path
inside the container before enabling this feature.

## Archive and recovery

Existing JSON records remain readable. New records include the expanded prompt,
constraint intent, selected composition, profile, seed, model/backend, precision,
quantization, dimensions, timing, validation state and attempt history. Reference
provenance and a checksum are recorded when used. Images and thumbnails keep the
existing checksum verification. Each candidate is written under
`data/candidates/<job>/<attempt>.png` before visual evaluation; staff can inspect
it if later steps fail. Candidates are not automatically shown to visitors.
Plan retention/cleanup for these files, which consume additional disk space.

Recovery restores valid completed archives even if a later database update marked
the job failed. Interrupted generation is not automatically billed or regenerated.
Approximate dHash metadata is recorded, but `PERCEPTUAL_DUPLICATE_DISTANCE=-1`
disables rejection by default. A threshold from 0 to 8 is experimental and must be
calibrated: similar stadium geometry is not necessarily a duplicate. Different
seeds are never described as proof of uniqueness.

Measured local results and remaining visual errors are recorded in
[benchmark-results.md](benchmark-results.md).

## Benchmark procedure

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark.py --output output/benchmarks/dry-run
LOCAL_IMAGE_DEVICE=mps .venv/bin/python scripts/benchmark.py --run --profile balanced --output output/benchmarks/mlx
LOCAL_IMAGE_DEVICE=cuda .venv/bin/python scripts/benchmark.py --run --profile balanced --output output/benchmarks/cuda
```

The fixed 50-case matrix includes athletics in mountains, retractable football,
coastal waves, a branching-tree entrance, desert passive cooling and combinations
of multi-select technologies/materials. `--pipeline` exercises the shared worker,
archive, optional evaluator and retries. Direct mode isolates adapter latency.
`--limit` supports a bounded pilot; `--prompt-set` accepts baseline records with
matching IDs, seeds and answers. Profiles and hardware must be reported separately.
JSON records retain prompts, durations, resolution, errors and device allocation
peaks. Device peaks are not total resident/system memory. Unavailable visual
scores, acceptance rates and critical failure rates remain null. Full visual
comparison requires a real evaluator or a documented human review rubric.

## Commercial licence verification

The official repository identifies the FLUX Kommunity licence. The locally saved
licence permits specified production use for qualifying users under its revenue
threshold, with additional conditions. Eligibility depends on the client and its
affiliates, not merely the developer. The client's eligibility and required content
filtering/review arrangements are not established in this repository; production
clearance remains unresolved. Retain the original licence and notices and confirm
terms with the client before a public kiosk deployment.

https://bfl.ai/licensing
