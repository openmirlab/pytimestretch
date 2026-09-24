"""Step 2 gate: the native _rubberband module builds, links, and runs.

Only engine_info() exists at this step — stretch() lands in step 3, so
available_backends() must still report no usable backend.
"""

import pytimestretch


def test_rubberband_module_imports() -> None:
    import pytimestretch._rubberband  # noqa: F401


def test_engine_info_reports_expected_keys() -> None:
    from pytimestretch import _rubberband

    info = _rubberband.engine_info()

    assert set(info) == {
        "engine",
        "version",
        "engine_version",
        "fft",
        "resampler",
        "source_revision",
    }
    assert info["engine"] == "rubberband"
    assert info["version"].startswith("4.0")
    assert info["engine_version"] == 3
    assert info["fft"] in {"builtin", "vdsp"}
    assert info["resampler"] == "bqresampler"
    assert len(info["source_revision"]) > 0


def test_available_backends_still_empty() -> None:
    # _rubberband exists but exposes no stretch() yet, so the registry
    # still reports it (and signalsmith, not built at all) as unavailable.
    assert pytimestretch.available_backends() == ()
