# Marker warp, pitch shift, and quality presets — plan

> Generated: 2026-09-24 · Source: Paul approved the scope "marker warp + pitch/formant + quality preset" after reviewing which engine features are worth exposing · Grounding: fresh — `stretch.py`, `_backends.py`, both native modules, and the vendored Rubber Band v4.0.0 / Signalsmith 1.3.2 headers

## Context

`time_stretch(audio, sample_rate, *, duration_ratio, backend)` works on both
engines with one global ratio, pitch held, and no engine options
(`src/pytimestretch/stretch.py`). Each native module implements
`stretch(buffer, sample_rate, duration_ratio, target_frames)`
(`native/rubberband_module.cpp`, `native/signalsmith_module.cpp`). The
[first plan](2026-09-24-binding-first-engines.md) listed pitch shift, key-frame
maps, and engine options as out of scope. Blind listening round 1 judged
Rubber Band best in all six cells.

Tactus needs three things this API cannot yet do: align transients to a grid
(warp markers), move a loop to a song's key (pitch shift, formant control
for voices), and trade quality for speed while an agent iterates.

Engine facts from the vendored headers:

- **Rubber Band.** `setKeyFrameMap(map<source frame, output frame>)`, offline
  only, set before the first `process()`; it does not set the overall ratio,
  so `setTimeRatio()` must match the final marker (present since v1.5).
  `setPitchScale()` is fixed in offline mode. `OptionFormantPreserved` works
  in R2 and R3; `setFormantScale()` is R3-only. `OptionTransients*`,
  `OptionDetector*`, `OptionPhase*`, and `OptionSmoothing*` affect R2 only.
  `OptionWindowShort` makes R3 "dramatically faster" at some quality cost
  and "may still sound better for non-percussive material than the R2 engine".
- **Signalsmith.** No key-frame map; each `process(in, nIn, out, nOut)` call
  stretches by `nOut/nIn`, and "it's up to you to make sure that the block
  lengths average out to the ratio you want". Rate changes centre on the
  processing time, so `inputLatency()`/`outputLatency()` matter for marker
  placement; `outputSeek()` pre-rolls and `flush()` drains. Pitch:
  `setTransposeSemitones()`. Formants: `setFormantFactor(f, compensatePitch)`
  with `setFormantBase()` (0 = auto-detect). `presetCheaper()` trades quality
  for speed.

## Resolved questions

- Scope: marker warp, pitch shift with formant control, and a two-level
  quality preset, on **both** engines (Paul, 2026-09-24).
- Public vocabulary follows musical intent and pyrubberband habits, not
  engine flags: `semitones`, `formants`, `quality`, `markers`.
- Out of this plan: custom formant offsets (`setFormantScale` /
  `setFormantSemitones`), material-specific transient presets (R2-only flags),
  `setFreqMap`, stereo `ChannelsTogether`, real-time streaming, Bungee.

## Proposed public contract (ratified by approving this plan)

```python
time_stretch(audio, sample_rate, *, duration_ratio,
             semitones=0.0, formants="shift", quality="high", backend="rubberband")
pitch_shift(audio, sample_rate, *, semitones,
            formants="shift", quality="high", backend="rubberband")
time_warp(audio, sample_rate, *, markers,
          semitones=0.0, formants="shift", quality="high", backend="rubberband")
```

| Aspect | Rule |
|---|---|
| `semitones` | Finite real; positive = up. `pitch_shift` is `time_stretch` at ratio 1.0 and requires it. |
| `formants` | `"shift"` (default, both engines' default) or `"preserve"` (keep the spectral envelope; for voices). |
| `quality` | `"high"` (default, current behavior), `"balanced"`, or `"fast"`. Rubber Band: R3 standard window / R3 + `OptionWindowShort` / R2 (`OptionEngineFaster`). Signalsmith: `presetDefault` / `presetCheaper` / unsupported → `UnsupportedOptionError` suggesting `"balanced"` (no silent aliasing). Measurements must confirm speed increases in that order. |
| `markers` | Sequence or `(K, 2)` array of integer `(source_frame, output_frame)`; first `(0, 0)`, last `(len(audio), output_frames)`; both columns strictly increasing; `K ≥ 2`. Output length is exactly the last output frame. A minimum marker spacing is set from step 3/4 measurements and enforced with an error naming it. |
| Placement | Each interior marker's source frame lands within a measured, pinned tolerance of its output frame. |
| Teaching errors | pyrubberband `n_steps=` → `semitones`; `time_map=` → `markers`; `rbargs=` → explain presets; existing `rate=` family unchanged. |
| Errors | New `UnsupportedOptionError(PytimestretchError, ValueError)` for an option an engine cannot honor. |
| Unchanged | Shapes, dtype preservation, exact length, immutability, existing error classes, no silent fallback. |

## Decided at plan review (2026-09-24)

- Round-2 listening material: pick loops directly from rytho-library (the
  surveyed drum, stereo hi-hat, bass, guitar, pad, vocal, and full-mix
  loops); they stay local and are never committed or published.
- Both Rubber Band fast variants are supported, as `quality="balanced"`
  (R3 + `OptionWindowShort`) and `quality="fast"` (R2). If measurements show
  R2 is not faster than R3 + `WindowShort`, or listening finds `"balanced"`
  no better than `"fast"`, record it and ask Paul whether to keep both.

## Approach

Each step keeps `uv run pytest -q` and `ruff` green; stop and report if a
gate fails.

0. **Refactor (behavior-preserving).** Move the validation helpers out of
   `stretch.py` into `src/pytimestretch/_validation.py` verbatim; `stretch.py`
   keeps only public functions. No test changes.
1. **Native contract v2 (behavior-preserving).** Replace each engine's
   `stretch(...)` with one entry point
   `render(buffer, sample_rate, markers, pitch_scale, preserve_formants, fast)`
   where `markers` is an int64 `(K, 2)` array. A plain stretch is the
   two-marker case `[(0, 0), (frames, target)]`: Rubber Band keeps its current
   path (no key-frame map for K = 2), Signalsmith keeps `.exact()`. The facade
   builds the markers; `_backends.py`'s header documents the new contract.
   Gate: every existing contract and engine test passes unchanged and the
   impulse measurements reproduce.
2. **Public API with a fake engine.** Add `pitch_shift`, `time_warp`, and the
   `semitones` / `formants` / `quality` parameters, marker validation, and the
   new teaching errors. Extend `tests/contract/` (fake engine) with marker
   validation, exact length from the last marker, pitch-shift length
   unchanged, and parameter errors.
3. **Rubber Band.** `setPitchScale`, `OptionFormantPreserved`,
   `setKeyFrameMap` plus `setTimeRatio` for K > 2, and both faster variants
   (`"balanced"`, `"fast"`).
   Measure: pitch accuracy (+7 and −5 semitones on sines), combined
   stretch + pitch, formant envelope stability on a synthetic vowel
   (preserve vs shift), marker placement on click trains across marker
   spacings (10, 25, 50, 100, 250 ms) and ratio jumps (×0.5 ↔ ×2 between
   neighbours), and speed of R3, R3 + `WindowShort`, and R2. Pin tolerances
   in `tests/engines/test_rubberband.py`.
4. **Signalsmith.** `setTransposeSemitones`, formant preservation via
   `setFormantFactor(1, compensatePitch=true)` with auto base, markers via
   variable-size `process()` blocks (block ≈ `intervalSamples()`) with
   `outputSeek()` pre-roll, `flush()`, and latency-compensated schedule, and
   `presetCheaper` for `"balanced"`; `"fast"` raises `UnsupportedOptionError`. Same measurements as step 3; pin tolerances.
   Short inputs keep the existing padding rule.
5. **Listening and docs.** Round-2 blind listening on real loops (material
   per open question 1): warp to a grid, ±semitone shifts with and without
   formant preservation on a vocal, and high vs balanced vs fast. Then update README
   (examples for all three functions), CLAUDE.md, CHANGELOG, measurement
   notes, and `plan.md`.

## Critical files

| File | Role and planned change |
|---|---|
| `src/pytimestretch/stretch.py` | Public `time_stretch`, `pitch_shift`, `time_warp`; builds markers and pitch scale. |
| `src/pytimestretch/_validation.py` (new) | Audio, sample-rate, ratio, marker, and parameter validation plus teaching errors (moved + extended). |
| `src/pytimestretch/_backends.py` | Documents native contract v2 (`render`). |
| `src/pytimestretch/__init__.py` | Exports the new functions. |
| `native/rubberband_module.cpp` | `render`: key-frame map, pitch, formant option, fast variant. |
| `native/signalsmith_module.cpp` | `render`: block-scheduled warp, transpose, formant compensation, `presetCheaper`. |
| `tests/contract/` | Marker/parameter contract on fake and both engines. |
| `tests/engines/test_rubberband.py`, `test_signalsmith.py` | Pinned pitch, formant, placement, and speed-relative checks. |
| `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/blueprints/` | Kept truthful per step. |

## Verification

- Every step: `uv sync --group dev --reinstall-package pytimestretch`,
  `uv run pytest -q`, `uv run ruff check .`, `uv build`.
- Step 1: existing suites and impulse measurements unchanged on both engines.
- Steps 3–4: measurement notes with engine revisions, pinned tolerances, and
  any marker spacing below which placement fails.
- Step 5: Paul's per-cell blind judgments recorded; README examples run as
  written.
- CI: the existing Linux wheel workflow must stay green locally
  (`cibuildwheel --only cp313-manylinux_x86_64`).

## Out of scope

Custom formant offsets, R2-only transient/detector/phase presets,
`setFreqMap`, stereo `ChannelsTogether`, time-varying pitch, real-time
streaming, Bungee, macOS/Windows CI, publication.
