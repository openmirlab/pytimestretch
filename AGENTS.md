# pytimestretch agent entry point

Read `CLAUDE.md`, then `README.md`. The package calls Rubber Band,
Signalsmith Stretch, and libpaulstretch C++ libraries directly through
nanobind modules compiled from vendored submodules. `time_stretch` in
`src/pytimestretch/stretch.py` owns the exact-length contract;
`extreme_stretch` in `src/pytimestretch/extreme.py` owns the separate
approximate-length creative contract. Keep README, CLAUDE.md, NOTICE,
CHANGELOG, and tests aligned with behavior changes. The combined package
is GPL-2.0-only; original pytimestretch code remains GPL-2.0-or-later.
Paul approved public GitHub source and the first validated source tag on
2026-09-24. PyPI publication still requires separate approval.
