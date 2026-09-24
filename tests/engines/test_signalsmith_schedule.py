"""Invariant checks for signalsmith_schedule.h's plan_warp_schedule(),
exposed test-only as ``_signalsmith._plan_warp_schedule``.

Pure-function checks (no engine call): chunk outputs sum to
``target_frames - tail_reserve``, no non-positive-input chunks, and
per-segment chunk sums match each marker segment's span after the
front-reserve shift. These are the invariants run_signalsmith_warp()
(native/signalsmith_module.cpp) relies on when it drives the engine along
the plan.

Reads: pytimestretch._signalsmith.
"""

from __future__ import annotations

import numpy as np
import pytest

from pytimestretch import _signalsmith as ss


def plan(markers, frames, target_frames, seek_len, interval):
    return ss._plan_warp_schedule(
        np.array(markers, dtype=np.int64), frames, target_frames, seek_len, interval
    )


@pytest.mark.parametrize(
    "markers,frames,target_frames,seek_len,interval",
    [
        ([[0, 0], [1500, 1600], [3000, 3000]], 3000, 3000, 200, 500),
        ([[0, 0], [1500, 1600], [3000, 3000]], 3000, 3000, 0, 500),
        ([[0, 0], [10, 20], [3000, 3000]], 3000, 3000, 200, 500),
        (
            [[0, 0], [500, 400], [1000, 900], [1500, 1600], [3000, 3000]],
            3000,
            3000,
            200,
            500,
        ),
        ([[0, 0], [50, 60], [100, 150]], 100, 150, 40, 30),
        ([[0, 0], [1, 1], [3000, 3000]], 3000, 3000, 200, 500),
    ],
)
def test_chunks_sum_to_process_end_output(markers, frames, target_frames, seek_len, interval):
    p = plan(markers, frames, target_frames, seek_len, interval)
    total_in = sum(c["input_count"] for c in p["chunks"])
    total_out = sum(c["output_count"] for c in p["chunks"])
    assert total_in == frames - p["seek_len"]
    assert total_out == p["process_end_output"]
    assert p["process_end_output"] + p["tail_reserve"] == target_frames


@pytest.mark.parametrize(
    "markers,frames,target_frames,seek_len,interval",
    [
        ([[0, 0], [1500, 1600], [3000, 3000]], 3000, 3000, 200, 500),
        ([[0, 0], [10, 20], [3000, 3000]], 3000, 3000, 200, 500),
        (
            [[0, 0], [500, 400], [1000, 900], [1500, 1600], [3000, 3000]],
            3000,
            3000,
            200,
            500,
        ),
    ],
)
def test_no_nonpositive_chunks_and_offsets_are_contiguous(
    markers, frames, target_frames, seek_len, interval
):
    p = plan(markers, frames, target_frames, seek_len, interval)
    expect_in = 0
    expect_out = 0
    for c in p["chunks"]:
        assert c["input_count"] > 0
        assert c["output_count"] > 0
        assert c["input_offset"] == expect_in
        assert c["output_offset"] == expect_out
        expect_in += c["input_count"]
        expect_out += c["output_count"]


def test_tail_reserve_bounds():
    p = plan([[0, 0], [1500, 1600], [3000, 3000]], 3000, 3000, 200, 500)
    assert 1 <= p["tail_reserve"] < 3000


def test_requires_at_least_three_markers():
    with pytest.raises(ValueError):
        plan([[0, 0], [3000, 3000]], 3000, 3000, 200, 500)
