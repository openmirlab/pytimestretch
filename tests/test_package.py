"""Smoke checks for the truthful bootstrap surface."""

import pytest

import pytimestretch


def test_version_is_importable() -> None:
    assert pytimestretch.__version__ == "0.0.0"


def test_stretch_is_explicitly_unimplemented() -> None:
    with pytest.raises(NotImplementedError, match="no audio backend"):
        pytimestretch.stretch_audio(
            object(), sample_rate=48_000, duration_ratio=1.5
        )
