# pytimestretch — maintainer context

Read [README.md](README.md) for the current user-facing contract and
[the development thought](docs/blueprints/thoughts/2026-09-24-time-stretch-package-contract.md)
before implementing a backend. OpenMIRLab's current constitution lives in the
adjacent `openmirlab-dev/plugins/openmirlab/CLAUDE.md`. This audio-tool package
is outside its usual inference-only template; treat that as a policy decision
to resolve, not an established exception.

## State and ownership

- Private GitHub repository; no PyPI publishing or public release approved.
- `time_stretch` (in `stretch.py`) owns the public contract: validation,
  teaching errors for pyrubberband/librosa habits (`rate=`, channels-first
  arrays), exact output length, and dtype preservation. `_backends.py` owns
  backend names and the native `stretch(buffer, sample_rate, duration_ratio,
  target_frames)` contract. Neither native engine module exists yet, so real
  backends raise `BackendUnavailableError`; `tests/contract/` runs against a
  test-only fake and will cover each engine as it lands.
- Authoring and musical decisions stay in callers. This package owns the
  NumPy-facing processing contract. Architecture is decided binding-first:
  call the Rubber Band and Signalsmith Stretch C++ libraries directly. Do not
  wrap `pyrubberband`/`python-stretch` (references only) and do not
  re-implement engine algorithms. The Python/Numba stretcher is a
  non-blocking research lane; never describe it as an engine replacement.
- The source version lives only in `src/pytimestretch/__about__.py`.
- `docs/blueprints/plan.md` is the status index; grounded plans and thoughts
  live in their sibling directories and are tracked in this repository.

## Development order

1. Pin the shared API with implementation-independent tests: duration ratio, audio
   shape, dtype, exact frame count, input immutability, and error behavior.
2. Build a minimal direct Rubber Band binding: in-memory buffers, parameter
   mapping, output placement, and a working build/install/licensing route.
   Never cite `pyrubberband` temporary-WAV results as binding precision or
   speed.
3. Bind Signalsmith Stretch behind the same facade; the same contract suite
   must pass on both engines.
4. Add real-audio fixtures, alignment checks, packaging tests, and listening
   evidence. Update README, this file, NOTICE, and CHANGELOG with each
   user-visible capability.

The Python research lane (blind listening, voice/mixed material, creative
control) runs in parallel and never gates these steps.

The thought is the detailed work specification; do not treat its proposed
interface as implemented behavior until tests and docs advance together.

## Verification

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check .
uv build
```

The engines are git submodules under `extern/` (Rubber Band v4.0.0,
Signalsmith Stretch 1.3.2 + main@57b93f4, Signalsmith Linear 0.3.1),
compiled by scikit-build-core/CMake into `pytimestretch._<engine>` modules;
never link a system library. `uv sync` installs non-editably, so after a C++
change run `uv sync --reinstall-package pytimestretch`. Tests stay offline;
the contract suite runs against every compiled engine plus a test-only fake.
Report engine revisions and build defines (`engine_info()`) with any
measurement.

## Licensing gate

Current `LICENSE` is private/no-redistribution. The `NOTICE` separates our
source from candidate wrappers and engines. Before making this public,
shipping a wheel with backend code, or enabling publishing, settle the
Rubber Band GPL/commercial linkage/distribution question and approve this
package's own public license.
