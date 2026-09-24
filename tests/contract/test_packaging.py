"""Installed-package packaging checks (currently: the ``py.typed`` marker).

Reads: pytimestretch.
"""

from __future__ import annotations

# --- Packaging -------------------------------------------------------------


def test_py_typed_marker_present_in_installed_package() -> None:
    import pathlib

    import pytimestretch

    package_dir = pathlib.Path(pytimestretch.__file__).parent
    assert (package_dir / "py.typed").is_file()
