"""Installed-package packaging checks for typing and combined licensing.

Reads: pytimestretch.
"""

from __future__ import annotations

from importlib.metadata import files, metadata

# --- Packaging -------------------------------------------------------------


def test_py_typed_marker_present_in_installed_package() -> None:
    import pathlib

    import pytimestretch

    package_dir = pathlib.Path(pytimestretch.__file__).parent
    assert (package_dir / "py.typed").is_file()


def test_combined_license_metadata_and_notices() -> None:
    assert metadata("pytimestretch")["License-Expression"] == "GPL-2.0-only"
    installed = files("pytimestretch")
    assert installed is not None
    names = {str(path) for path in installed}
    for suffix in (
        "licenses/LICENSE",
        "licenses/NOTICE",
        "licenses/licenses/nanobind-LICENSE",
        "licenses/extern/libpaulstretch/COPYING",
        "licenses/extern/libpaulstretch/vendor/kissfft/COPYING_kiss_fft.txt",
        "licenses/extern/bungee/LICENSE",
        "licenses/extern/bungee/submodules/eigen/COPYING.MPL2",
        "licenses/licenses/pffft-LICENSE",
    ):
        assert any(name.endswith(suffix) for name in names)
