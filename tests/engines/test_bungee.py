"""Bungee Basic alignment and pitch evidence for the position-curve binding."""

from __future__ import annotations

import numpy as np

import pytimestretch as pts


def test_isolated_impulse_alignment_at_forward_and_reverse_speeds() -> None:
    sample_rate = 48_000
    frames = 4 * sample_rate
    audio = np.zeros(frames, dtype=np.float32)
    audio[sample_rate] = 1.0
    for ratio in (0.5, 1.0, 1.5, 3.0):
        output_frames = round(frames * ratio)
        output = pts.time_scrub(
            audio, sample_rate,
            control_points=[(0, 0), (output_frames, frames)],
        )
        assert abs(np.argmax(np.abs(output)) - round(sample_rate * ratio)) <= 2

    reverse = pts.time_scrub(
        audio, sample_rate,
        control_points=[(0, frames), (frames, 0)],
    )
    assert abs(np.argmax(np.abs(reverse)) - 3 * sample_rate) <= 2


def test_100_ms_click_train_alignment() -> None:
    sample_rate = 48_000
    frames = 4 * sample_rate
    audio = np.zeros(frames, dtype=np.float32)
    clicks = np.arange(sample_rate // 10, frames, sample_rate // 10)
    audio[clicks] = 1.0
    output = pts.time_scrub(
        audio, sample_rate,
        control_points=[(0, 0), (frames * 3 // 2, frames)],
    )
    for source in clicks:
        expected = source * 3 // 2
        region = output[expected - 24:expected + 24]
        assert np.max(np.abs(region)) > 0.1
        assert abs(np.argmax(np.abs(region)) - 24) <= 2


def test_global_pitch_is_independent_of_hold_speed() -> None:
    sample_rate = 48_000
    frames = 2 * sample_rate
    audio = (0.2 * np.sin(2 * np.pi * 440 * np.arange(frames) / sample_rate)).astype(
        np.float32
    )
    points = [(0, 0), (sample_rate, sample_rate), (2 * sample_rate, sample_rate)]
    base = pts.time_scrub(audio, sample_rate, control_points=points)
    shifted = pts.time_scrub(audio, sample_rate, control_points=points, semitones=7)

    def dominant_frequency(audio: np.ndarray, start: int, end: int) -> float:
        segment = audio[start:end]
        window = np.hanning(len(segment))
        fft = np.fft.rfft(segment * window)
        return float(np.fft.rfftfreq(len(segment), 1 / sample_rate)[np.argmax(abs(fft))])

    for start, end in ((int(0.3 * sample_rate), int(0.8 * sample_rate)),
                       (int(1.3 * sample_rate), int(1.8 * sample_rate))):
        original_pitch = dominant_frequency(base, start, end)
        raised_pitch = dominant_frequency(shifted, start, end)
        # Basic's stationary grain has a small pitch bias (about 1.4% in
        # this case), but the requested transposition still applies.
        assert abs(raised_pitch - original_pitch * 2 ** (7 / 12)) < 5


def test_bungee_engine_info_is_basic_and_pinned() -> None:
    from pytimestretch import _bungee

    assert _bungee.engine_info() == {
        "engine": "bungee",
        "edition": "Basic",
        "version": "2.4.30",
        "source_revision": "8cb6977d0c1a1b411ac320493b3c7f5182ed2d22",
        "fft": "PFFFT",
    }
