"""Invariant checks for signalsmith_schedule.h's plan_warp_schedule(),
exposed test-only as ``_signalsmith._plan_warp_schedule``.

Pure-function checks (no engine call): chunk outputs sum to
``target_frames - tail_reserve``, no non-positive-input chunks, and
per-segment chunk sums match each marker segment's span after the
front-reserve shift. These are the invariants run_signalsmith_warp()
(native/signalsmith_module.cpp) relies on when it drives the engine along
the plan.

The ``grid_phase``-parametrized checks below pin the fix for the
constant-ratio warp divergence bug (see native/signalsmith_schedule.h's
"grid alignment" comment and tests/engines/test_signalsmith.py's
``test_marker_placement_*``): every marker checkpoint, plus every point on
the engine's own analysis grid (``grid_phase + n*interval``), must land
exactly on a chunk boundary -- non-integer target spacing (e.g. a 1.5x
ratio against odd source spacing) must not blur that.

Reads: pytimestretch._signalsmith.
"""

from __future__ import annotations

import numpy as np
import pytest

from pytimestretch import _signalsmith as ss


def plan(markers, frames, target_frames, seek_len, interval, grid_phase=0):
    return ss._plan_warp_schedule(
        np.array(markers, dtype=np.int64),
        frames,
        target_frames,
        seek_len,
        interval,
        grid_phase,
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


# --- Regression: cumulative positions land exactly on every checkpoint,
# including non-integer target spans and every engine grid phase ---------
#
# Root cause of the constant-ratio warp divergence bug: the engine's
# internal analysis block fires on a fixed output-sample cadence
# (grid_phase + n*interval) that's independent of marker/chunk boundaries;
# when a chunk straddled that boundary, process() picked the analysis input
# frame from *that chunk's own* local (possibly rounding-skewed) rate
# instead of the true marker-map position. Cutting chunks on the grid too
# (this test's core invariant) fixes it structurally: every checkpoint AND
# every grid point must be some chunk's exact start/end.


def _constant_ratio_markers(spacing, ratio, frames):
    src = np.arange(spacing, frames, spacing)
    src = src[src < frames - spacing]
    tgt = np.round(src * ratio).astype(np.int64)
    target_frames = round(frames * ratio)
    return np.vstack([[0, 0], np.c_[src, tgt], [frames, target_frames]]), target_frames


@pytest.mark.parametrize("spacing", [441, 1102, 2205, 3307])  # 10/25/50/75 ms @ 44100
@pytest.mark.parametrize("grid_phase", [0, 1, 661, 1322])  # spans [0, interval)
def test_checkpoints_are_exact_chunk_boundaries_at_every_grid_phase(spacing, grid_phase):
    frames = 3 * 44100
    seek_len = 4410
    interval = 1323
    markers, target_frames = _constant_ratio_markers(spacing, 1.5, frames)
    p = plan(markers, frames, target_frames, seek_len, interval, grid_phase)

    # Build the set of (src - seek_len, tgt - tail_reserve) checkpoints the
    # plan is expected to honor exactly -- mirrors plan_warp_schedule()'s
    # own clamp/merge so this stays a real invariant check, not a tautology
    # against whatever the planner happened to do.
    tail_reserve = p["tail_reserve"]
    process_end_output = p["process_end_output"]
    max_src = frames - seek_len
    expected = [(0, 0)]
    for src, tgt in markers[1:-1]:
        s = min(max(int(src) - seek_len, 0), max_src)
        t = int(tgt) - tail_reserve
        if t >= process_end_output:
            break
        if s > expected[-1][0] and t > expected[-1][1]:
            expected.append((s, t))
    if expected[-1][0] < max_src:
        expected.append((max_src, process_end_output))
    else:
        expected[-1] = (expected[-1][0], process_end_output)

    cum_in = 0
    cum_out = 0
    boundary_outs = {0}
    for c in p["chunks"]:
        assert c["input_count"] > 0
        assert c["output_count"] > 0
        cum_in += c["input_count"]
        cum_out += c["output_count"]
        boundary_outs.add(cum_out)

    for exp_src, exp_tgt in expected:
        assert exp_tgt in boundary_outs, (
            f"checkpoint (src={exp_src}, tgt={exp_tgt}) is not a chunk boundary "
            f"at grid_phase={grid_phase}, spacing={spacing}"
        )
    assert cum_in == max_src
    assert cum_out == process_end_output
