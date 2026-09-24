/**
 * signalsmith_schedule.h — pure marker-warp schedule planner for the
 * Signalsmith Stretch K > 2 (warp) path.
 *
 * `plan_warp_schedule()` derives the checkpoint/chunk sequence
 * `run_signalsmith_warp()` (signalsmith_module.cpp) drives the engine
 * along: pre-roll front-shift and merge, the front_reserve/tail-reserve
 * algebra, and per-segment chunking at ~`interval` frames with cumulative
 * rounding. Makes no engine calls, so its invariants are directly checkable
 * -- see `_plan_warp_schedule()` and test_signalsmith_schedule.py.
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
 * Plan the warp schedule for `markers` ((source, target) pairs including
 * the (0, 0) and (frames, target_frames) ends, K >= 3) over an input of
 * `frames` samples rendering to `target_frames`, given the engine's
 * `seek_len` (outputSeekLength() for the overall rate) and `interval`
 * (intervalSamples(), the target chunk size).
 *
 * Mirrors run_signalsmith_warp()'s derivation exactly (see that function's
 * own header comment in signalsmith_module.cpp for the full rationale):
 * shift every marker's source left by seek_len (real input already
 * consumed by the pre-roll), shift every target after the first left by a
 * constant front_reserve = round(seek_len * segment_0_local_rate) so every
 * segment's local ratio survives the front cut exactly, merge forward any
 * marker whose shifted source doesn't advance past the previous kept
 * checkpoint (it falls inside the pre-roll window), then chunk each
 * consecutive checkpoint pair at ~interval input frames with a running
 * cumulative round so chunk outputs sum to the segment's exact span.
 */
inline WarpSchedule plan_warp_schedule(
    const std::vector<std::pair<int64_t, int64_t>> &markers, int64_t frames,
    int64_t target_frames, int64_t seek_len, int64_t interval) {
    if (seek_len < 0) seek_len = 0;
    if (interval < 1) interval = 1;

    size_t k = markers.size();
    if (k < 3) {
        throw std::invalid_argument(
            "plan_warp_schedule: markers must have at least 3 rows (K > 2), got " +
            std::to_string(k));
    }

    double front_rate = static_cast<double>(markers[1].second - markers[0].second) /
                         static_cast<double>(markers[1].first - markers[0].first);
    int64_t tail_reserve = static_cast<int64_t>(std::llround(seek_len * front_rate));
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

    for (size_t i = 0; i + 1 < cps.size(); ++i) {
        int64_t seg_in = cps[i + 1].src - cps[i].src;
        int64_t seg_out = cps[i + 1].tgt - cps[i].tgt;
        int64_t base_in_offset = cps[i].src;
        int64_t base_out_offset = cps[i].tgt;
        int64_t consumed_in = 0;
        int64_t consumed_out = 0;
        while (consumed_in < seg_in) {
            int64_t chunk_in = std::min<int64_t>(interval, seg_in - consumed_in);
            int64_t cumulative_out = static_cast<int64_t>(std::llround(
                static_cast<double>(consumed_in + chunk_in) *
                static_cast<double>(seg_out) / static_cast<double>(seg_in)));
            int64_t chunk_out = cumulative_out - consumed_out;
            plan.chunks.push_back({base_in_offset + consumed_in,
                                    base_out_offset + consumed_out, chunk_in,
                                    chunk_out});
            consumed_in += chunk_in;
            consumed_out += chunk_out;
        }
    }

    return plan;
}

}  // namespace pytimestretch::native
