# pytimestretch — maintainer context

Read [README.md](README.md) for the current user-facing contract, install
workflow, and upstream acknowledgments before implementing a backend.
OpenMIRLab's current constitution lives in the adjacent `openmirlab-dev/plugins/openmirlab/CLAUDE.md`. This audio-tool package
is outside its usual inference-only template. Its compiled audio-tool scope
and public GitHub source are explicitly approved by Paul; a general org
audio-tool category remains a separate policy follow-up.

## State and ownership

- Public GitHub source approved by Paul on 2026-09-24 after the Tactus trial.
  The first source tag, `v0.1.0`, is approved after verification.
  No PyPI publishing is approved. Keep the
  `Private :: Do Not Upload` classifier as the package-upload guard.
- `stretch.py` holds the public functions `time_stretch`, `pitch_shift`,
  and `time_warp`, which all build a marker array and share one private
  render path (buffer copy, dispatch, result checks, dtype restore).
  `_validation.py` owns every input rule and the teaching errors for
  pyrubberband/librosa habits (`rate=`, `n_steps=`, `time_map=`, `rbargs=`,
  channels-first arrays). `_backends.py` owns backend names and native
  contract v2: `render(buffer, sample_rate, markers, pitch_scale,
  preserve_formants, quality)`; each native module declares
  `SUPPORTED_QUALITY` (the one owner of engine capability).
  `native/rubberband_module.cpp` (offline R3, `OptionChannelsApart`,
  key-frame map without the leading `(0, 0)`) and
  `native/signalsmith_module.cpp` (`.exact()` for two markers, a scheduled
  `outputSeek`/`process`/`flush` stream for more, fixed seed, short input
  zero-padded) implement it. `tests/contract/` runs against every built engine
  plus a test-only fake; `tests/engines/` pins engine-specific measurements.
- `extreme.py` owns the separate `extreme_stretch` operation backed by
  libpaulstretch v0.3.0 through `_paulstretch`. It passes the requested
  ratio through unchanged and returns the native output length; it is not
  an interchangeable `_backends` entry. It requires at least 81,920 frames,
  accepts mono/stereo and ratios >= 1e-5; ratios below 1 shorten audio with
  especially approximate duration on short clips. It randomizes spectral
  phase across calls. A native mutex protects upstream's process-global
  non-atomic seed counter from concurrent calls.
- Authoring and musical decisions stay in callers. This package owns the
  NumPy-facing processing contract. Architecture is decided binding-first:
  call the Rubber Band, Signalsmith Stretch, and libpaulstretch C++ libraries
  directly. Do not wrap `pyrubberband`/`python-stretch` (references only) or
  re-implement engine algorithms. The Python/Numba stretcher is a
  non-blocking research lane; never describe it as an engine replacement.
- The source version lives only in `src/pytimestretch/__about__.py`.
- `docs/blueprints/` contains optional local planning and measurement notes.
  Keep it untracked, ignored, and excluded from distributions. Public docs and
  verification must stand alone without these files.

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
5. Bind libpaulstretch separately for creative extreme stretching. Preserve
   its native ratio and approximate duration, as chosen in the blind vocal
   comparison; keep the original three functions' exact-length contract.

The Python research lane (blind listening, voice/mixed material, creative
control) runs in parallel and never gates these steps.

The README and executable tests define implemented behavior. If local design
notes are present, treat proposed interfaces as plans until tests and docs
advance together.

## Install and attribution

This is a Python package with C++ native extensions. Document installation
through uv: source checkout uses `uv sync --python 3.12 --no-dev`; a downloaded
wheel uses `uv venv --python 3.12` and `uv pip install <matching-wheel>`.
Run user scripts with `uv run --no-project python <script>` in that environment.
Source builds require a C++20 toolchain; matching wheels contain all three
engines. The existing Rubber Band and Signalsmith targets remain C++17.

README acknowledgments credit the engine and binding authors and the reference
projects pedalboard, pylibrb, python-stretch, and pyrubberband with their specific
contributions. Keep that provenance aligned with NOTICE.

## Verification

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check .
uv build
```

The default suite excludes two `performance`-marked, host-dependent speed
comparisons. Run `uv run pytest -q -m performance` explicitly on a controlled
host. Audio correctness and quality-preset behavior remain in the default
suite; a shared runner's timing ratio is not a portable correctness contract.

The engines are git submodules under `extern/` (Rubber Band v4.0.0,
Signalsmith Stretch 1.3.2 + main@57b93f4, Signalsmith Linear 0.3.1,
libpaulstretch v0.3.0 with bundled KissFFT),
compiled by scikit-build-core/CMake into `pytimestretch._<engine>` modules;
never link a system library. `uv sync` installs non-editably, so after a C++
change run `uv sync --reinstall-package pytimestretch`. Tests stay offline;
the contract suite runs against every compiled engine plus a test-only fake.
Report engine revisions and build defines (`engine_info()`) with any
measurement.

Linux wheel CI runs on pull requests and `main` pushes. The separate
`wheels-all-platforms.yml` workflow builds macOS arm64/x86_64 and Windows
AMD64 wheels only for PRs labeled `all-platforms` or manual dispatches.
All three platforms test installed CPython 3.10–3.13 wheels and log
`engine_info()`; wheels are Actions artifacts and no workflow publishes a
package release.

## Licensing gate

The combined package is GPL-2.0-only because its distributions include
libpaulstretch v0.3.0. Original pytimestretch code and Rubber Band retain
their GPL-2.0-or-later grants; the combination is conveyed under GPLv2.
`NOTICE` lists every vendored component, its pinned revision, and license.
Update `NOTICE` whenever a submodule revision or a statically linked
dependency changes. Paul's 2026-09-24 public-source approval supersedes the
earlier private-repository gate. Keep the `Private :: Do Not Upload`
classifier until PyPI publication is separately approved.
