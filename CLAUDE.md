# pytimestretch — maintainer context

Read [README.md](README.md) for the current user-facing contract and
[the development thought](docs/blueprints/thoughts/2026-09-24-time-stretch-package-contract.md)
before implementing a backend. OpenMIRLab's current constitution lives in the
adjacent `openmirlab-dev/plugins/openmirlab/CLAUDE.md`. This audio-tool package
is outside its usual inference-only template; treat that as a policy decision
to resolve, not an established exception.

## State and ownership

- Private GitHub repository; no PyPI publishing or public release approved.
- The package only imports and raises a deliberate `NotImplementedError` for
  `stretch_audio`. Neither engine is operational here yet.
- Authoring and musical decisions stay in callers. This package owns the
  NumPy-facing processing contract. Whether its implementation should be a
  direct C++ binding or a Python/NumPy/SciPy/Numba engine is open; run the
  deciding probe in the development thought before locking the architecture.
- The source version lives only in `src/pytimestretch/__about__.py`.
- `docs/blueprints/plan.md` is the status index; grounded plans and thoughts
  live in their sibling directories and are tracked in this repository.

## Development order

1. Pin the shared API with implementation-independent tests: duration ratio, audio
   shape, dtype, exact frame count, input immutability, and error behavior.
2. Run the Python/Numba-versus-native-engine deciding probe on real material,
   including blind listening and measured timing/alignment.
3. Choose the smallest architecture supported by that evidence: direct
   bindings, a Python engine, or a hybrid. Existing Python wrappers remain
   useful references but are not assumed production dependencies.
4. Implement the chosen path with real-audio fixtures, marker/alignment
   checks, packaging tests, and listening evidence. Update README, this file,
   NOTICE, and CHANGELOG with each user-visible capability.

The thought is the detailed work specification; do not treat its proposed
interface as implemented behavior until tests and docs advance together.

## Verification

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check .
uv build
```

For future backend tests, use opt-in integration markers and report the exact
engine library revisions and build configurations. Default tests must remain
offline and run without either backend installed.

## Licensing gate

Current `LICENSE` is private/no-redistribution. The `NOTICE` separates our
source from candidate wrappers and engines. Before making this public,
shipping a wheel with backend code, or enabling publishing, settle the
Rubber Band GPL/commercial linkage/distribution question and approve this
package's own public license.
