"""Step 2/3/4 gate: both native modules build, link, and run.

Step 3 landed _rubberband's stretch() alongside engine_info(); step 4 lands
_signalsmith the same way, so available_backends() now reports both.
"""

import pytimestretch


def test_rubberband_module_imports() -> None:
    import pytimestretch._rubberband  # noqa: F401


def test_signalsmith_module_imports() -> None:
    import pytimestretch._signalsmith  # noqa: F401


def test_paulstretch_module_imports() -> None:
    import pytimestretch._paulstretch  # noqa: F401


def test_paulstretch_engine_info_reports_pinned_build() -> None:
    from pytimestretch import _paulstretch

    info = _paulstretch.engine_info()
    assert info == {
        "engine": "libpaulstretch",
        "version": "0.3.0",
        "source_revision": info["source_revision"],
        "fft": "KISSFFT",
        "fft_size": 4096,
        "min_input_frames": 81920,
        "onset_detection": False,
    }
    assert info["source_revision"] in {
        "v0.3.0",  # sdist has sources but no submodule .git metadata
        "d2de02f1632188ab17f80bd1bfeab98a729cffa9",
    }


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


def test_signalsmith_engine_info_reports_expected_keys() -> None:
    from pytimestretch import _signalsmith

    info = _signalsmith.engine_info()

    assert set(info) == {
        "engine",
        "version",
        "source_revision",
        "linear_revision",
        "fft",
        "preset",
        "seed",
    }
    assert info["engine"] == "signalsmith"
    assert info["version"].startswith("1.3")
    assert info["fft"] in {"builtin", "accelerate"}
    assert info["preset"] == "default"
    assert len(info["source_revision"]) > 0
    assert len(info["linear_revision"]) > 0
    assert isinstance(info["seed"], int)


def test_available_backends_reports_both_engines() -> None:
    # Both native modules are built as of step 4.
    assert pytimestretch.available_backends() == ("rubberband", "signalsmith")
