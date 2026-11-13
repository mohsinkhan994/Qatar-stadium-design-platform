# Local generation benchmark — 13 November 2026

## Scope and method

Measured on the developer's Apple Silicon Mac (reported M5 Pro, 24 GB unified
memory), using the cached FLUX 3 Image Klein Q4 conversion, MFLUX 0.24.0 and
MLX 0.32.4. All runs are local; no paid API was used. The benchmark records actual
latency around adapter calls, including first-use initialization. Requests run
serially with weights retained between images. There was no NVIDIA hardware
available, so CUDA compatibility has automated adapter tests, not a hardware
performance result.

The repeatable matrix contains 50 different answer combinations with fixed seeds
1000–1049. All use the same 16-step distilled checkpoint. The balanced run uses
1024 × 576 pixels. Raw prompts, seeds, answers, metadata and PNGs are retained in
`output/benchmarks/` (ignored by Git). These include visitor proposals that cannot
be verified from an image, such as smart systems and water-reuse performance.

## Balanced results

- Generated: **50 of 50**, with **zero generation errors**.
- Mean latency: **25.85 seconds**; warm mean: **25.84 seconds**.
- First image: **26.57 seconds**; observed range: **23.74–28.42 seconds**.
- Maximum reported MLX allocation: **7.24 GB** (decimal).

MLX allocation is not total process RAM, macOS memory pressure or a guarantee
that the app needs only 7.24 GB. Queue waiting time is excluded. Two simultaneously
submitted kiosk requests are served serially; the second includes the first
request's remaining generation time.

## Profile and pipeline smoke tests

| Run | Images | Resolution | Mean latency | Errors |
| --- | ---: | --- | ---: | ---: |
| Old captions, updated adapter | 2 | 1024 × 576 | 25.14 s | 0 |
| New captions, balanced | 50 | 1024 × 576 | 25.85 s | 0 |
| New captions, fast preview | 2 | 768 × 512 | 19.66 s | 0 |
| New captions, high quality | 1 | 1344 × 768 | 48.26 s | 0 |
| Full worker and archive, balanced | 2 | 1024 × 576 | 28.92 s | 0 |
| Reference-guided worker and archive | 1 | 1024 × 576 | 73.24 s | 0 |

Reference guidance was also exercised through the actual MLX edit adapter using
an internally generated athletics image. It completed and archived successfully;
this verifies the execution path, not improved visual adherence. Its first-use
latency was substantially higher than text-only generation.

The full worker smoke test completed both archives with no retries and correctly
recorded unavailable visual validation. Small profile samples are exploratory,
not stable latency distributions. Differences between separate runs can include
thermal state and background load. Machine-readable aggregates are retained in
[benchmark-metrics.json](benchmark-metrics.json).

## Matched prompt comparison

Baseline prompts were reconstructed from commit
`f6c18bce25d13dbe5251794394307ecadc32b289`, before this change. Cases 1 and 2 use
identical answers, resolved signatures, seeds, dimensions, checkpoint and sampling
steps. Both baseline and new captions run through the same updated adapter, so
this comparison isolates prompts; it does **not** measure the old subprocess
loading overhead or establish an end-to-end speedup.

An informal visual review of case 1 found:

| Requirement | Old caption | New structured caption |
| --- | --- | --- |
| Mountain setting | Visible | Visible |
| Athletics track | No recognizable track; football-style field | Clearly visible oval track |
| Eight correct lanes | Not satisfied | Not verified; lane count/geometry needs assessment |
| Open-to-sky bowl | Perimeter canopy visible | Far-side canopy remains visible |

This is one qualitative observation, not a statistical quality score. The revised
caption improves the primary field geometry in this example but does not reliably
enforce every critical constraint. Case 3 shows a coastal setting, but the requested
sculptural waterfront promenade is not clearly established. Case 4 does not clearly
express its branching-tree entrance. Prompting alone is insufficient to guarantee
signature details or exact roof configurations.

## Accuracy limits and deployment gates

No real image evaluator is configured. Overall quality score, critical visual
failure rate and visually verified first-attempt acceptance are **unavailable**;
50 successful renders must not be reported as 100% visual accuracy. Conditional
visual retries are tested with synthetic evaluator responses, not claimed as a
measured quality improvement. Exact duplicate checks remain separate.

Keep balanced as the default. Higher resolution is an output-size choice, not
proof of higher accuracy. Before public deployment, configure and calibrate a
pixel-based evaluator or establish a documented human acceptance review, test the
CUDA deployment on its target GPU, and resolve the client's commercial licence
eligibility. See [generation-quality.md](generation-quality.md) for configuration,
reference provenance, timeout limitations and the evaluator contract.
