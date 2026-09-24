# pytimestretch agent entry point

Read `CLAUDE.md`, then `README.md`. The package calls Rubber Band and
Signalsmith Stretch C++ libraries directly through nanobind modules compiled
from vendored submodules; `time_stretch` in `src/pytimestretch/stretch.py`
owns the public contract. Keep README, CLAUDE.md, NOTICE, CHANGELOG, and
tests aligned with any behavior change. The package is GPL-2.0-or-later.
Paul approved public GitHub source and the first validated source tag on
2026-09-24. PyPI publication still requires separate approval.
