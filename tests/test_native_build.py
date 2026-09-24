"""Step 2/3 gate: the native _rubberband module builds, links, and runs.

Step 3 adds stretch() alongside engine_info(), so available_backends() now
reports "rubberband" (signalsmith is still unbuilt until step 4).
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


def test_available_backends_reports_rubberband_only() -> None:
    # _rubberband now exposes stretch(); signalsmith is not built until
    # step 4, so it stays excluded.
    assert pytimestretch.available_backends() == ("rubberband",)
