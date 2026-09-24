# pytimestretch package bootstrap — plan

> Generated: 2026-09-24 · Source: Paul-approved name, OpenMIRLab private-repo setup, and Tactus time-stretch probes · Grounding: current OpenMIRLab constitution, sibling packages, and upstream wrappers

## Context

`openmirlab/pytimestretch` is a newly created private, initially empty repository. Tactus currently treats Rubber Band as its working time-stretch baseline and has investigated Signalsmith Stretch as a second algorithm. The existing Python access paths differ: `pyrubberband` invokes an external CLI through temporary files, while `python-stretch` is a compiled NumPy-facing binding. A direct Python binding to the C++ libraries is one product hypothesis; a Python/NumPy/SciPy/Numba implementation is another. The bootstrap must not decide this architecture before the proposed comparative probe.

The first change establishes a truthful, installable package shell and an implementation note. It does not claim that stretching works yet. Python source remains the authoring surface; this package will own backend adaptation, not creative choice or Tactus arrangement policy.

## Resolved questions

- Name and distribution/import spelling: `pytimestretch`.
- GitHub home: `openmirlab/pytimestretch`, private for now. No PyPI publication.
- Comparison scope: Rubber Band, Signalsmith Stretch, and one focused Python/NumPy/SciPy/Numba prototype. Existing Python wrappers are references, not assumed runtime dependencies.
- Package policy: the bootstrap stays pure Python. If the product uses native extensions, OpenMIRLab's no-compiled-core and inference-only rules need an explicit audio-tool exception before claiming policy conformance; even a Python-only DSP package needs its scope acknowledged.
- This is a bootstrap, not the first audio backend implementation.

## Open questions

- Before public release: decide the source license and distribution topology, especially Rubber Band's GPL/commercial license. The private bootstrap can carry a no-redistribution license notice without pretending that upstream licenses transfer to this package.
- After the deciding probe: if using bindings, decide whether each C++ library is linked dynamically, linked into a wheel, or supplied through an external installation. This affects licenses, binary sizes, and the install promise; it does not block the shell.
- Before exposing a stable API: ratify the exact ratio, channel-axis, length, marker, and error semantics against real audio. The thought records a proposed contract and verification matrix.

## Approach

1. Create the private repository with a development branch, then add a Hatchling `src/` package with a single-sourced version and a version import smoke test. The public audio call remains an explicit `NotImplementedError` stub.
2. Add README and maintainer guidance that distinguish currently working behavior from the intended backend workflow. Record the private licensing state and upstream attribution in LICENSE/NOTICE.
3. Add a tracked `docs/blueprints/` plan index and a developer-ready thought covering backend boundaries, candidate API, test fixtures, decision gates, and implementation order.
4. Run package, test, and wheel-install smoke checks; inspect the wheel for only intended files. Commit on a branch and merge to `main` through GitHub rather than directly moving `main`.

## Critical files

| File | Role and planned change |
| --- | --- |
| `pyproject.toml` | Package metadata, optional-backend boundary, Hatchling build, verification dependencies. |
| `src/pytimestretch/__about__.py` | Single version source. |
| `src/pytimestretch/__init__.py` and `stretch.py` | Honest import surface and explicit unfinished audio operation. |
| `tests/test_package.py` | Version and stub contract smoke tests. |
| `README.md` and `CLAUDE.md` | Paired user/maintainer reality gate. |
| `LICENSE` and `NOTICE` | Private source status and upstream license separation. |
| `docs/blueprints/plan.md` and `thoughts/2026-09-24-time-stretch-package-contract.md` | Durable development handoff. |

## Verification

- `uv sync --group dev`, `uv run pytest -q`, and `uv build` succeed without installing either backend.
- A clean environment can install the built wheel and import `pytimestretch.__version__`.
- Calling the audio stub fails loudly; README never shows it as working.
- The wheel does not bundle Rubber Band, Signalsmith, temporary audio, or experimental Tactus files.
- Confirm the GitHub repository remains private and `main` is updated only through a merge.

Bootstrap check on 2026-09-24: two smoke tests passed in an offline-installed
editable environment; system Ruff 0.16.0 passed; `uv build --offline` produced
an sdist and pure-Python wheel; that wheel installed into a clean environment
and imported version `0.0.0`. A complete `uv sync --group dev` was attempted
but could not download the lockfile's Ruff 0.16.8 wheel in this environment;
the package and tests were verified by installing cached pytest separately.
The normal locked sync remains a follow-up check when network access succeeds.

## Out of scope

No audio processing implementation, engine vendoring, PyPI release, public visibility change, Tactus integration, or universal claim about sonic quality in this bootstrap.
