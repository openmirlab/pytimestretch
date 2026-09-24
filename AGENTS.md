# pytimestretch agent entry point

Read `CLAUDE.md`, then `README.md`. The package calls Rubber Band and
Signalsmith Stretch C++ libraries directly through nanobind modules compiled
from vendored submodules; `time_stretch` in `src/pytimestretch/stretch.py`
owns the public contract. Keep README, CLAUDE.md, NOTICE, CHANGELOG, and
tests aligned with any behavior change. The package is GPL-2.0-or-later and
the repository stays private and unpublished until Paul approves release.
