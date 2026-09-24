/**
 * signalsmith_schedule.h — pure marker-warp schedule planner for the
 * Signalsmith Stretch K > 2 (warp) path.
 *
 * `plan_warp_schedule()` derives the checkpoint/chunk sequence
 * `run_signalsmith_warp()` (signalsmith_module.cpp) drives the engine
 * along: pre-roll front-shift and merge, the front_reserve/tail-reserve
 * algebra (now via a full piecewise-linear evaluation of the original
 * marker map, not just the first segment's rate), and chunking cut on the
 * engine's own analysis grid (`grid_phase` + multiples of `interval`) in
 * addition to marker checkpoints, so every internal `process()` call that
 * lands on an analysis boundary starts a chunk exactly at that boundary --
 * see the "grid alignment" rationale below. Makes no engine calls, so its
 * invariants are directly checkable -- see `_plan_warp_schedule()` and
 * test_signalsmith_schedule.py.
 *
 * Reads: <cstdint>, <utility>, <vector>.
 */

#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>

namespace pytimestretch::native {

/** One process() call: `input_count` input frames starting at
 * `seek_len + input_offset` in the original buffer, producing
 * `output_count` output frames starting at `output_offset`. */
struct WarpChunk {
    int64_t input_offset;
    int64_t output_offset;
    int64_t input_count;
    int64_t output_count;
};

/** The full plan for run_signalsmith_warp(): the process() chunk sequence,
 * the flush() tail (`tail_reserve` frames starting at `process_end_output`,
 * synthesized at `last_rate`), and `seek_len` echoed back for convenience. */
struct WarpSchedule {
    std::vector<WarpChunk> chunks;
    int64_t seek_len;
    int64_t tail_reserve;
    int64_t process_end_output;  // == target_frames - tail_reserve
    double last_rate;
};

/**
 * Evaluate the original (unshifted) marker map's target value at source
 * position `src`, by piecewise-linear interpolation across however many
 * marker segments `src` spans (not just the first one). Used to derive
 * `front_reserve`/`tail_reserve` as "how much output the pre-roll's
 * seek_len input frames are actually worth", per the *real* marker map --
 * using only the first segment's rate (as an earlier version did) is only
 * correct when seek_len doesn't outrun that segment's own span, which
 * dense markers (spacing below seek_len, e.g. every 10-25 ms against a
 * ~100 ms pre-roll) routinely violate.
 */
inline double marker_target_at(const std::vector<std::pair<int64_t, int64_t>> &markers,
                                int64_t src) {
    size_t k = markers.size();
    size_t i = 0;
    while (i + 2 < k && markers[i + 1].first <= src) ++i;
    int64_t seg_in = markers[i + 1].first - markers[i].first;
    int64_t seg_out = markers[i + 1].second - markers[i].second;
    if (seg_in <= 0) return static_cast<double>(markers[i].second);
    double frac = static_cast<double>(src - markers[i].first) / static_cast<double>(seg_in);
    return static_cast<double>(markers[i].second) + frac * static_cast<double>(seg_out);
}

/**
 * Plan the warp schedule for `markers` ((source, target) pairs including
 * the (0, 0) and (frames, target_frames) ends, K >= 3) over an input of
 * `frames` samples rendering to `target_frames`, given the engine's
 * `seek_len` (outputSeekLength() for the overall rate) and `interval`
 * (intervalSamples(), the target chunk size). `grid_phase` (default 0) is
 * the engine's own analysis-grid phase after outputSeek() -- the local
 * output index, within this schedule's first process() chunk, at which the
 * next internal analysis block fires (0 when the pre-roll's outputLatency()
 * lands exactly on an interval multiple, as it does for the "high" preset;
 * nonzero presets like "balanced" need it computed from
 * `outputLatency() % intervalSamples()`, see run_signalsmith_warp()).
 *
 * Mirrors run_signalsmith_warp()'s derivation exactly (see that function's
 * own header comment in signalsmith_module.cpp for the full rationale):
 * shift every marker's source left by seek_len (real input already
 * consumed by the pre-roll), shift every target after the first left by a
 * constant front_reserve = round(marker_target_at(seek_len)) (the real
 * piecewise-linear map's value, not just the first segment's rate) so
 * every segment's local ratio survives the front cut exactly, merge
 * forward any marker whose shifted source doesn't advance past the
 * previous kept checkpoint (it falls inside the pre-roll window), then cut
 * chunks at every checkpoint AND at every point on the engine's own
 * analysis grid (`grid_phase + n * interval`) -- see "grid alignment"
 * below -- with the input position at each grid cut computed by
 * piecewise-linear interpolation within its checkpoint segment, so chunk
 * outputs still sum to each segment's exact span with no drift.
 *
 * Grid alignment rationale: the engine's `process()` fires an internal
 * analysis block whenever its own `samplesSinceLast` output-sample counter
 * (persistent across process() calls) reaches `interval`; when it fires
 * mid-call, it picks the input frame to analyse via `round(local_output_
 * index * this_call's_inputSamples / this_call's_outputSamples)` -- a
 * *local* linear interpolation using only that one call's own (possibly
 * off-nominal, cumulative-rounding-driven) rate, not the true position
 * along the marker map. Cutting a chunk exactly at each analysis-grid
 * point makes that block always fire at `local_output_index == 0` of some
 * chunk, so the interpolation above is trivially exact (0/n == 0) and the
 * *real* analysis position -- computed here from the marker map, not
 * process()'s local guess -- lands untouched. Verified by measurement (see
 * the development thought): without this, constant-ratio markers whose
 * spacing straddles `interval` unevenly (25 ms with the "high" preset's
 * ~30 ms interval is a clean multiple and was already accurate; 10/50/75 ms
 * are not) diverged progressively from a plain stretch at the same ratio,
 * the classic white-noise decorrelation signature of an accumulating
 * sub-sample timing error, not a placement error large enough to see in
 * click tests alone.
 */
inline WarpSchedule plan_warp_schedule(
    const std::vector<std::pair<int64_t, int64_t>> &markers, int64_t frames,
    int64_t target_frames, int64_t seek_len, int64_t interval,
    int64_t grid_phase = 0) {
    if (seek_len < 0) seek_len = 0;
    if (interval < 1) interval = 1;
    grid_phase = ((grid_phase % interval) + interval) % interval;

    size_t k = markers.size();
    if (k < 3) {
        throw std::invalid_argument(
            "plan_warp_schedule: markers must have at least 3 rows (K > 2), got " +
            std::to_string(k));
    }

    int64_t seek_clamped = std::clamp<int64_t>(seek_len, 0, markers.back().first);
    int64_t tail_reserve =
        static_cast<int64_t>(std::llround(marker_target_at(markers, seek_clamped)));
    tail_reserve = std::max<int64_t>(tail_reserve, 1);
    tail_reserve = std::min<int64_t>(tail_reserve, target_frames - 1);
    int64_t process_end_output = target_frames - tail_reserve;

    double last_rate =
        static_cast<double>(markers[k - 1].second - markers[k - 2].second) /
        static_cast<double>(markers[k - 1].first - markers[k - 2].first);

    struct Checkpoint {
        int64_t src;
        int64_t tgt;
    };
    std::vector<Checkpoint> cps;
    cps.push_back({0, 0});
    int64_t max_src = frames - seek_len;
    for (size_t i = 1; i + 1 < k; ++i) {
        int64_t src = markers[i].first - seek_len;
        int64_t tgt = markers[i].second - tail_reserve;
        if (tgt >= process_end_output) break;
        src = std::clamp<int64_t>(src, 0, max_src);
        if (src > cps.back().src && tgt > cps.back().tgt) {
            cps.push_back({src, tgt});
        }
    }
    if (cps.back().src < max_src) {
        cps.push_back({max_src, process_end_output});
    } else {
        cps.back().tgt = process_end_output;
    }

    WarpSchedule plan;
    plan.seek_len = seek_len;
    plan.tail_reserve = tail_reserve;
    plan.process_end_output = process_end_output;
    plan.last_rate = last_rate;

    // Cut points on the OUTPUT axis: every checkpoint after the first (kept
    // exact, using the checkpoint's own src -- no interpolation) plus every
    // point on the engine's analysis grid strictly between 0 and
    // process_end_output (grid_phase + n*interval; when grid_phase == 0 the
    // grid already includes 0 itself, which needs no cut since it's the
    // schedule's start). Sorted and de-duplicated so a grid point that
    // lands exactly on a checkpoint contributes one cut, not two.
    std::vector<int64_t> cuts;
    cuts.reserve(cps.size() + static_cast<size_t>(process_end_output / interval) + 2);
    for (size_t i = 1; i < cps.size(); ++i) cuts.push_back(cps[i].tgt);
    int64_t first_grid = (grid_phase == 0) ? interval : grid_phase;
    for (int64_t g = first_grid; g < process_end_output; g += interval) cuts.push_back(g);
    std::sort(cuts.begin(), cuts.end());
    cuts.erase(std::unique(cuts.begin(), cuts.end()), cuts.end());

    size_t seg = 0;  // current bracket is [cps[seg], cps[seg + 1]]
    int64_t prev_out = 0;
    int64_t prev_in = 0;
    for (int64_t o : cuts) {
        while (seg + 2 < cps.size() && cps[seg + 1].tgt < o) ++seg;
        int64_t in_pos;
        if (o == cps[seg + 1].tgt) {
            in_pos = cps[seg + 1].src;
        } else {
            int64_t seg_in = cps[seg + 1].src - cps[seg].src;
            int64_t seg_out = cps[seg + 1].tgt - cps[seg].tgt;
            in_pos = cps[seg].src + static_cast<int64_t>(std::llround(
                         static_cast<double>(o - cps[seg].tgt) *
                         static_cast<double>(seg_in) / static_cast<double>(seg_out)));
        }
        int64_t chunk_out = o - prev_out;
        int64_t chunk_in = in_pos - prev_in;
        if (chunk_out > 0 && chunk_in > 0) {
            plan.chunks.push_back({prev_in, prev_out, chunk_in, chunk_out});
            prev_out = o;
            prev_in = in_pos;
        }
        // A degenerate cut (chunk_in <= 0, possible only from a grid point
        // landing within a sample of a checkpoint under an extreme local
        // ratio) is simply skipped: prev_out/prev_in stay put and the next
        // cut's chunk absorbs its span, keeping every emitted chunk's
        // input_count/output_count strictly positive.
        if (o == cps[seg + 1].tgt && seg + 2 < cps.size()) ++seg;
    }
    // Final chunk from the last cut (or 0, if there were none -- a K == 3
    // schedule whose only checkpoint is the end) up to process_end_output.
    if (prev_out < process_end_output) {
        plan.chunks.push_back({prev_in, prev_out, max_src - prev_in,
                                process_end_output - prev_out});
    }

    return plan;
}

}  // namespace pytimestretch::native
