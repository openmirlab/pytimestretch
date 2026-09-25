# pytimestretch agent entry point

Read `CLAUDE.md`, then `README.md`. The package binds Rubber Band,
Signalsmith Stretch, libpaulstretch, and Bungee Basic C++ sources directly
through nanobind. `stretch.py` owns the shared exact-length backend contract;
`extreme.py` owns approximate-length spectral stretching; `scrub.py` owns
exact-length hold/reverse position control. Keep README, CLAUDE.md, NOTICE,
CHANGELOG, and tests aligned with behavior changes. The combined package
is GPL-2.0-only; original pytimestretch code remains GPL-2.0-or-later.
Paul approved public GitHub source and the first validated source tag on
2026-09-24. PyPI publication still requires separate approval.
