/**
 * signalsmith_module.cpp — nanobind entry point for pytimestretch._signalsmith.
 *
 * ★ Implements native contract v2 in full, matching
 * native/rubberband_module.cpp's structure: `render(buffer, sample_rate,
 * markers, pitch_scale, preserve_formants, quality) ->
 * float32[channels, markers[-1][1]]`. `markers` with `K == 2` run
 * `run_signalsmith_exact()` (`.exact()`, short-input pad-and-trim);
 * `K > 2` (warp) run `run_signalsmith_warp()`, a scheduled
 * `outputSeek()`/`process()`/`flush()` stream planned by
 * signalsmith_schedule.h. `configure_engine()` is the one place that maps
 * (quality, pitch_scale, preserve_formants) onto engine calls;
 * `validate_render()` (contract v2 checks) picks which run_* path a call
 * takes.
 *
 * Reads: render_contract.h, signalsmith_schedule.h,
 * signalsmith-stretch/signalsmith-stretch.h (vendored,
 * extern/signalsmith-stretch).
 */

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

// signalsmith-linear/fft.h calls std::memcpy without including <cstring>
// itself (known upstream gap, not patched here — see CLAUDE.md's vendoring
// policy); render_contract.h includes <cstring> transitively, but include
// it explicitly here too, before the vendored headers below, so this file
// does not depend on that ordering accident.
#include <cstring>

#include <algorithm>
#include <cmath>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "render_contract.h"
#include "signalsmith-stretch/signalsmith-stretch.h"
#include "signalsmith_schedule.h"

namespace nb = nanobind;
using signalsmith::stretch::SignalsmithStretch;
using pytimestretch::native::channel_pointers;
using pytimestretch::native::InputBuffer;
using pytimestretch::native::make_output;
using pytimestretch::native::MarkersBuffer;
using pytimestretch::native::plan_warp_schedule;
using pytimestretch::native::validate_common;
using pytimestretch::native::WarpSchedule;

#ifndef PYTIMESTRETCH_SS_FFT
#define PYTIMESTRETCH_SS_FFT "builtin"
#endif

#ifndef PYTIMESTRETCH_SS_SOURCE_REVISION
#define PYTIMESTRETCH_SS_SOURCE_REVISION "main@57b93f4"
#endif

#ifndef PYTIMESTRETCH_SS_LINEAR_REVISION
#define PYTIMESTRETCH_SS_LINEAR_REVISION "0.3.1"
#endif

namespace {

// A fixed seed makes the phase-randomization used internally for
// transient/peak handling deterministic across runs, which the contract
// suite's determinism test requires; 0x5eed is an arbitrary but memorable
// constant, not a tuned value.
constexpr long kSeed = 0x5eed;

/** Channel-indexable adapter over raw pointers, satisfying the `Inputs`/
 * `Outputs` template concept the engine expects: `buffer[channel][index]`.
 * `operator[]` returns a raw pointer, which already supports `[index]`. */
template <typename T>
struct ChannelPointers {
    std::vector<T *> ptrs;
    T *operator[](int c) const { return ptrs[static_cast<size_t>(c)]; }
};

/** A view over a ChannelPointers-like object that adds a fixed sample
 * offset to every channel — the binding's own equivalent of the header's
 * private `OffsetIO` (used internally by its `exact()`/`outputSeek()`, not
 * accessible to callers), needed here to feed process() a moving window
 * into one shared buffer across a sequence of calls without copying. */
template <typename Base>
struct OffsetView {
    const Base &base;
    long offset;
    auto operator[](int c) const -> decltype(base[c]) { return base[c] + offset; }
};

template <typename Base>
OffsetView<Base> offset_view(const Base &base, long offset) {
    return OffsetView<Base>{base, offset};
}

struct StretchDiagnostics {
    bool exact_ok = false;
    bool padded = false;
    int input_latency = 0;
    int output_latency = 0;
    int block_samples = 0;
    int interval_samples = 0;
    size_t padded_frames = 0;
    std::string path;  // "exact" (K == 2) or "warp" (K > 2)
};

/** Contract v2 inputs, resolved and validated by validate_render(). */
struct RenderInputs {
    size_t channels;
    size_t frames;
    size_t target_frames;
    std::vector<std::pair<int64_t, int64_t>> markers;  // (source, target), K rows
};

/** Configure `stretch` per the resolved quality/pitch/formant options.
 * Shared by both the exact() and warp paths so there is exactly one place
 * that knows how contract v2's (pitch_scale, preserve_formants, quality)
 * map onto SignalsmithStretch calls. Throws std::invalid_argument for an
 * unknown `quality` (defense in depth; the facade already gates on
 * SUPPORTED_QUALITY, and rejects "fast" outright at validation, before
 * calling render() at all). */
void configure_engine(SignalsmithStretch<float> &stretch, size_t channels,
                       size_t sample_rate, double pitch_scale,
                       bool preserve_formants, const std::string &quality) {
    if (quality == "high") {
        stretch.presetDefault(static_cast<int>(channels),
                               static_cast<float>(sample_rate));
    } else if (quality == "balanced") {
        // splitComputation=false: that flag trades latency for spreading a
        // block's work across more process() calls, which this binding's
        // whole-buffer-at-once calls have no use for.
        stretch.presetCheaper(static_cast<int>(channels),
                               static_cast<float>(sample_rate),
                               /*splitComputation=*/false);
    } else {
        throw std::invalid_argument("signalsmith: quality \"" + quality +
                                     "\" is not one of \"high\", \"balanced\"");
    }
    stretch.setTransposeFactor(static_cast<float>(pitch_scale));
    if (preserve_formants) {
        // compensatePitch=true: the header's own formant-compensation
        // section documents this as adjusting the formant multiplier for
        // the current pitch shift, i.e. it is what keeps the spectral
        // envelope in place while the transpose moves the pitch — a plain
        // multiplier of 1 without it would leave the envelope shifting
        // along with the pitch (== "shift" behavior).
        stretch.setFormantFactor(1.0f, /*compensatePitch=*/true);
        stretch.setFormantBase(0);  // 0 = auto-detect fundamental
    }
}

/**
 * Run the Signalsmith Stretch whole-buffer pipeline for the plain
 * two-marker case: construct with `kSeed`, configure, and call `.exact()`.
 *
 * `.exact()` requires `frames >= outputSeekLength(playbackRate)` (its
 * internal seek/pre-roll requirement); below that it zero-fills the
 * output and returns `false` rather than stretching anything — measured,
 * this threshold sits around one block-and-interval's worth of samples
 * (tens of ms at 44.1/48 kHz with `presetDefault`'s sizing), well inside
 * ordinary clip lengths the contract suite exercises (e.g. a 4410-frame
 * stereo fixture at 48 kHz), not just the plan's "very short" edge cases
 * (1 or 10 frames). Silently zeroing real, short-but-normal audio would
 * fail the engine-independent contract, so short input here is
 * zero-padded up to the required length (plus one block of margin, since
 * `outputSeekLength`'s own float rounding makes the exact boundary
 * unreliable), the output size scaled to keep the same duration ratio,
 * `.exact()` run once on the padded buffers, and only the caller's
 * original `target_frames` taken from the front of that output — the
 * same "pad and trim" idea python-stretch's own bindings use by hand
 * (they predate `.exact()`); here it only engages below `.exact()`'s own
 * minimum, not on every call. If `.exact()` still reports failure,
 * `render()` raises rather than returning its zero-fill, so the binding
 * never passes silence off as a stretch.
 *
 * `output_data` must already be sized `channels * target_frames`,
 * C-contiguous, per-channel stride `target_frames`.
 *
 * Runs with the GIL released by the caller; touches no Python state.
 */
StretchDiagnostics run_signalsmith_exact(const std::vector<const float *> &input,
                                          size_t channels, size_t frames,
                                          size_t sample_rate, size_t target_frames,
                                          double pitch_scale,
                                          bool preserve_formants,
                                          const std::string &quality,
                                          float *output_data) {
    SignalsmithStretch<float> stretch(kSeed);
    configure_engine(stretch, channels, sample_rate, pitch_scale,
                      preserve_formants, quality);

    double duration_ratio =
        static_cast<double>(target_frames) / static_cast<double>(frames);
    float playback_rate =
        static_cast<float>(static_cast<double>(frames) /
                            static_cast<double>(target_frames));
    int seek_length = stretch.outputSeekLength(playback_rate);

    size_t proc_frames = frames;
    size_t proc_target = target_frames;
    std::vector<std::vector<float>> padded;  // kept alive if padding is used
    std::vector<const float *> proc_ptrs = input;
    bool did_pad = false;

    if (seek_length > 0 && frames < static_cast<size_t>(seek_length)) {
        did_pad = true;
        // Margin beyond the estimated threshold: outputSeekLength() mixes
        // a float playbackRate into an int return, so the boundary it
        // reports is not exact; one extra block+interval keeps the padded
        // call comfortably clear of it without materially changing cost
        // (padding is already only reached for short, cheap inputs).
        proc_frames = static_cast<size_t>(seek_length) +
                      static_cast<size_t>(stretch.blockSamples()) +
                      static_cast<size_t>(stretch.intervalSamples());
        proc_target = std::max<size_t>(
            target_frames,
            static_cast<size_t>(std::llround(
                static_cast<double>(proc_frames) * duration_ratio)));

        padded.assign(channels, std::vector<float>(proc_frames, 0.0f));
        for (size_t c = 0; c < channels; ++c) {
            std::memcpy(padded[c].data(), input[c], frames * sizeof(float));
        }
        proc_ptrs.resize(channels);
        for (size_t c = 0; c < channels; ++c) {
            proc_ptrs[c] = padded[c].data();
        }
    }

    ChannelPointers<const float> in{proc_ptrs};

    std::vector<float> proc_output(channels * proc_target, 0.0f);
    ChannelPointers<float> out;
    out.ptrs.resize(channels);
    for (size_t c = 0; c < channels; ++c) {
        out.ptrs[c] = proc_output.data() + c * proc_target;
    }

    StretchDiagnostics diag;
    diag.path = "exact";
    diag.exact_ok = stretch.exact(in, static_cast<int>(proc_frames), out,
                                   static_cast<int>(proc_target));
    diag.padded = did_pad;
    diag.padded_frames = proc_frames;
    diag.input_latency = stretch.inputLatency();
    diag.output_latency = stretch.outputLatency();
    diag.block_samples = stretch.blockSamples();
    diag.interval_samples = stretch.intervalSamples();

    for (size_t c = 0; c < channels; ++c) {
        std::memcpy(output_data + c * target_frames,
                    proc_output.data() + c * proc_target,
                    target_frames * sizeof(float));
    }
    return diag;
}

/**
 * Run the marker-warp (K > 2) pipeline over an already long-enough buffer
 * (frames >= the pre-roll requirement; run_signalsmith_warp() below pads
 * first when that doesn't hold). `markers` is the full (source, target)
 * list including the (0, 0) and (frames, target_frames) ends.
 *
 * Schedule, mirroring what `.exact()` does internally for the whole
 * buffer:
 *
 *  1. `outputSeek(input, seek_len)` where `seek_len =
 *     outputSeekLength(overall playbackRate)` — the same pre-roll `.exact()`
 *     would use for a single-ratio stretch of this duration; the pre-roll's
 *     job is priming the STFT analysis window with context, not tracking
 *     any one segment's local ratio, so the overall ratio is the right
 *     input here, same as `.exact()` uses for the whole buffer.
 *  2. Build "checkpoints" (shifted_source, shifted_target) from the
 *     markers: shift every source coordinate left by `seek_len` (frames
 *     already consumed as pre-roll context, clamped at 0), and shift every
 *     target coordinate (after the first) left by a constant
 *     `front_reserve = round(seek_len * segment_0_local_rate)` — this is
 *     what keeps every segment's own local (input span / output span)
 *     ratio exactly equal to its nominal marker ratio despite the front
 *     cut, the same algebraic cancellation that makes `.exact()`'s own
 *     single call ratio-exact (see the function body for the derivation);
 *     shifting only the source side (an earlier version of this function
 *     did) leaves segment 0 inflated and every later segment deflated by
 *     the same amount, which measured as a large constant placement error
 *     at every marker after the first. `front_reserve` doubles as the
 *     tail reserved for flush() at the very end (the deficit it
 *     represents is finally repaid there); flush()'s own `playbackRate`
 *     argument instead uses the *last* segment's local rate, since that
 *     governs how the zero-padded tail should be synthesized. Any marker
 *     whose shifted source coordinate does not advance past the
 *     previous kept checkpoint (i.e. it falls entirely inside the pre-roll
 *     window, so there is no real input left to dedicate to it) is merged
 *     forward onto the next checkpoint that does have real input — this is
 *     the "floor" the plan asks to measure and explain rather than paper
 *     over.
 *  3. For each consecutive checkpoint pair, call process() once per chunk
 *     of ~intervalSamples() input frames, with each chunk's output count
 *     computed from a running cumulative round (`round(consumed_in_total *
 *     segment_output_span / segment_input_span)`) so the chunks within one
 *     segment sum to that segment's exact output span with no drift, and
 *     the sequence of process() calls overall consumes exactly
 *     `frames - seek_len` input frames (all the real audio the pre-roll
 *     didn't already absorb).
 *  4. `flush()` for the reserved tail, using the last segment's local
 *     ratio as its `playbackRate` argument (governs how much silent input
 *     the tail simulates internally).
 *
 * Runs with the GIL released by the caller; touches no Python state.
 */
StretchDiagnostics run_signalsmith_warp(
    const std::vector<const float *> &input, size_t channels, size_t frames,
    size_t sample_rate, size_t target_frames,
    const std::vector<std::pair<int64_t, int64_t>> &markers, double pitch_scale,
    bool preserve_formants, const std::string &quality, float *output_data) {
    SignalsmithStretch<float> stretch(kSeed);
    configure_engine(stretch, channels, sample_rate, pitch_scale,
                      preserve_formants, quality);

    double overall_rate =
        static_cast<double>(frames) / static_cast<double>(target_frames);
    int seek_len = stretch.outputSeekLength(static_cast<float>(overall_rate));
    if (seek_len < 0) seek_len = 0;
    // Caller (run_signalsmith_warp_padded) guarantees frames > seek_len.

    ChannelPointers<const float> in_full{
        std::vector<const float *>(input.begin(), input.end())};

    stretch.outputSeek(in_full, seek_len);

    std::vector<float> out_buf(channels * target_frames, 0.0f);
    ChannelPointers<float> out_full;
    out_full.ptrs.resize(channels);
    for (size_t c = 0; c < channels; ++c) {
        out_full.ptrs[c] = out_buf.data() + c * target_frames;
    }

    // The pre-roll's front cut (seek_len real input frames given to
    // outputSeek() instead of process()) has to be compensated on the
    // OUTPUT side too, or every process() call downstream of segment 0
    // inherits a wrong local ratio — verified by measurement (see the
    // development thought): shifting only the source coordinates (as an
    // earlier version of this function did) left segment 0 inflated and
    // every later segment deflated by the same constant amount, which
    // measured as a large constant placement error at every marker after
    // the first, not just a "floor" near the very start.
    //
    // The fix mirrors exact()'s own algebra. exact()'s single process()
    // call reduces inputSamples by seek_len and outputSamples by
    // seek_len * overall_rate together, which cancels exactly (outputIndex
    // / inputSamples == overall_rate algebraically) — that is what keeps
    // a single-ratio exact() call's placement accurate throughout,
    // including near the very start. Generalizing: reduce segment 0's own
    // *target* coordinate by seek_len * (segment 0's own local rate) —
    // call this `front_reserve` — so segment 0's own local ratio is
    // exactly preserved. Every later marker's target then carries that
    // same constant `front_reserve` deficit forward (subtracting a
    // constant from every target after the first leaves every *later*
    // segment's own input/output span — hence its local ratio — exactly
    // as it was before shifting, the same shift-invariance argument that
    // already applies to the source side). The deficit is finally repaid
    // by flush() at the very end, so `front_reserve` doubles as the
    // reserved tail length — analogous to exact()'s own tail reservation,
    // generalized from "the one overall rate" to "segment 0's rate",
    // since segment 0 is where the deficit actually originates. Any marker
    // whose shifted source doesn't advance past the previous kept
    // checkpoint (it falls inside the pre-roll window) is merged forward
    // onto the next checkpoint that has real input to spare. See
    // signalsmith_schedule.h's plan_warp_schedule() for the derivation and
    // the chunking/rounding that follows it.
    WarpSchedule plan = plan_warp_schedule(
        markers, static_cast<int64_t>(frames), static_cast<int64_t>(target_frames),
        seek_len, stretch.intervalSamples());

    for (const auto &chunk : plan.chunks) {
        stretch.process(offset_view(in_full, seek_len + chunk.input_offset),
                         static_cast<int>(chunk.input_count),
                         offset_view(out_full, chunk.output_offset),
                         static_cast<int>(chunk.output_count));
    }

    int64_t flush_len = plan.tail_reserve;
    stretch.flush(offset_view(out_full, plan.process_end_output),
                  static_cast<int>(flush_len), static_cast<float>(plan.last_rate));

    StretchDiagnostics diag;
    diag.path = "warp";
    diag.exact_ok = true;
    diag.padded = false;
    diag.padded_frames = frames;
    diag.input_latency = stretch.inputLatency();
    diag.output_latency = stretch.outputLatency();
    diag.block_samples = stretch.blockSamples();
    diag.interval_samples = stretch.intervalSamples();

    for (size_t c = 0; c < channels; ++c) {
        std::memcpy(output_data + c * target_frames, out_buf.data() + c * target_frames,
                    target_frames * sizeof(float));
    }
    return diag;
}

/** Entry point for the warp path: pads (buffer and markers, proportionally
 * scaled) when `frames` is below the pre-roll requirement, same "pad and
 * trim" idea as the exact() path, then delegates to
 * run_signalsmith_warp() and trims back to the caller's target_frames. */
StretchDiagnostics run_signalsmith(
    const std::vector<const float *> &input, size_t channels, size_t frames,
    size_t sample_rate, size_t target_frames,
    const std::vector<std::pair<int64_t, int64_t>> &markers, double pitch_scale,
    bool preserve_formants, const std::string &quality, float *output_data) {
    if (markers.size() == 2) {
        return run_signalsmith_exact(input, channels, frames, sample_rate,
                                      target_frames, pitch_scale,
                                      preserve_formants, quality, output_data);
    }

    // Probe seek_len with a throwaway stretch configured the same way, to
    // decide whether padding is needed before doing any real work.
    SignalsmithStretch<float> probe(kSeed);
    configure_engine(probe, channels, sample_rate, pitch_scale,
                      preserve_formants, quality);
    double overall_rate =
        static_cast<double>(frames) / static_cast<double>(target_frames);
    int seek_len = probe.outputSeekLength(static_cast<float>(overall_rate));
    if (seek_len < 0) seek_len = 0;

    if (frames > static_cast<size_t>(seek_len)) {
        return run_signalsmith_warp(input, channels, frames, sample_rate,
                                     target_frames, markers, pitch_scale,
                                     preserve_formants, quality, output_data);
    }

    // Short-input branch: pad the buffer and proportionally scale every
    // marker's coordinates by the same pad ratio, run the warp pipeline on
    // the padded call, then trim back to target_frames — mirroring
    // run_signalsmith_exact()'s "pad and trim" for the two-marker case.
    size_t proc_frames = static_cast<size_t>(seek_len) +
                          static_cast<size_t>(probe.blockSamples()) +
                          static_cast<size_t>(probe.intervalSamples());
    double pad_ratio = static_cast<double>(proc_frames) / static_cast<double>(frames);
    size_t proc_target = std::max<size_t>(
        target_frames,
        static_cast<size_t>(std::llround(static_cast<double>(target_frames) * pad_ratio)));

    std::vector<std::vector<float>> padded(channels, std::vector<float>(proc_frames, 0.0f));
    for (size_t c = 0; c < channels; ++c) {
        std::memcpy(padded[c].data(), input[c], frames * sizeof(float));
    }
    std::vector<const float *> proc_ptrs(channels);
    for (size_t c = 0; c < channels; ++c) proc_ptrs[c] = padded[c].data();

    std::vector<std::pair<int64_t, int64_t>> proc_markers;
    proc_markers.reserve(markers.size());
    for (auto [src, tgt] : markers) {
        int64_t proc_src = static_cast<int64_t>(std::llround(src * pad_ratio));
        int64_t proc_tgt = static_cast<int64_t>(std::llround(tgt * pad_ratio));
        proc_markers.emplace_back(proc_src, proc_tgt);
    }
    proc_markers.front() = {0, 0};
    proc_markers.back() = {static_cast<int64_t>(proc_frames), static_cast<int64_t>(proc_target)};
    // Keep strictly increasing after independent rounding.
    for (size_t i = 1; i < proc_markers.size(); ++i) {
        if (proc_markers[i].first <= proc_markers[i - 1].first) {
            proc_markers[i].first = proc_markers[i - 1].first + 1;
        }
        if (proc_markers[i].second <= proc_markers[i - 1].second) {
            proc_markers[i].second = proc_markers[i - 1].second + 1;
        }
    }
    proc_markers.back() = {static_cast<int64_t>(proc_frames), static_cast<int64_t>(proc_target)};

    std::vector<float> proc_output(channels * proc_target, 0.0f);
    StretchDiagnostics diag = run_signalsmith_warp(
        proc_ptrs, channels, proc_frames, sample_rate, proc_target, proc_markers,
        pitch_scale, preserve_formants, quality, proc_output.data());
    diag.padded = true;
    diag.padded_frames = proc_frames;

    for (size_t c = 0; c < channels; ++c) {
        std::memcpy(output_data + c * target_frames,
                    proc_output.data() + c * proc_target, target_frames * sizeof(float));
    }
    return diag;
}

/**
 * Validate the shared inputs to render()/_stretch_diagnostics() and return
 * (channels, frames, target_frames, markers): delegates the contract v2
 * checks common to both bindings (buffer shape, sample_rate, marker
 * shape/count, pitch_scale) to render_contract.h's validate_common(), then
 * adds this engine's own field (the raw marker list; Rubber Band's
 * equivalent instead builds a key-frame map). `quality` is resolved later,
 * in configure_engine(), which is the single place that knows this
 * engine's quality names.
 */
RenderInputs validate_render(const InputBuffer &buffer, int sample_rate,
                              const MarkersBuffer &markers, double pitch_scale,
                              bool preserve_formants,
                              const std::string &quality) {
    (void)preserve_formants;
    (void)quality;
    auto common =
        validate_common(buffer, sample_rate, markers, pitch_scale, "signalsmith");
    size_t k = markers.shape(0);

    RenderInputs in;
    in.channels = common.channels;
    in.frames = common.frames;
    in.target_frames = common.target_frames;
    in.markers.reserve(k);
    for (size_t i = 0; i < k; ++i) {
        in.markers.emplace_back(markers(i, 0), markers(i, 1));
    }
    return in;
}

nb::ndarray<nb::numpy, float, nb::ndim<2>> render(InputBuffer buffer,
                                                    int sample_rate,
                                                    MarkersBuffer markers,
                                                    double pitch_scale,
                                                    bool preserve_formants,
                                                    std::string quality) {
    RenderInputs in = validate_render(buffer, sample_rate, markers,
                                       pitch_scale, preserve_formants,
                                       quality);

    auto out = make_output(in.channels, in.target_frames);
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, in.channels, in.frames);
        StretchDiagnostics diag;
        {
            nb::gil_scoped_release release;
            diag = run_signalsmith(in_ptrs, in.channels, in.frames,
                                    static_cast<size_t>(sample_rate),
                                    in.target_frames, in.markers, pitch_scale,
                                    preserve_formants, quality, out.data());
        }
        if (!diag.exact_ok) {
            // out's capsule frees the buffer on unwind; no manual delete[].
            throw std::runtime_error(
                "signalsmith: could not process " + std::to_string(in.frames) +
                " input frames into " + std::to_string(in.target_frames) +
                " output frames (padded to " +
                std::to_string(diag.padded_frames) + ")");
        }
    }

    return out;
}

/** Measurement-only variant sharing run_signalsmith() and validate_render():
 * reports whether the exact() or streamed (warp) path ran, whether the
 * input needed pad-and-trim, and the engine's block/interval/latency
 * sizes, instead of the audio itself. */
nb::dict stretch_diagnostics(InputBuffer buffer, int sample_rate,
                              MarkersBuffer markers, double pitch_scale,
                              bool preserve_formants, std::string quality) {
    RenderInputs in = validate_render(buffer, sample_rate, markers,
                                       pitch_scale, preserve_formants,
                                       quality);

    std::vector<float> scratch(in.channels * in.target_frames);
    StretchDiagnostics diag;
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, in.channels, in.frames);
        nb::gil_scoped_release release;
        diag = run_signalsmith(in_ptrs, in.channels, in.frames,
                                static_cast<size_t>(sample_rate),
                                in.target_frames, in.markers, pitch_scale,
                                preserve_formants, quality, scratch.data());
    }

    nb::dict info;
    info["exact_ok"] = diag.exact_ok;
    info["padded"] = diag.padded;
    info["padded_frames"] = diag.padded_frames;
    info["input_latency"] = diag.input_latency;
    info["output_latency"] = diag.output_latency;
    info["block"] = diag.block_samples;
    info["interval"] = diag.interval_samples;
    info["path"] = diag.path.c_str();
    return info;
}

/** Test-only exposure of plan_warp_schedule() (signalsmith_schedule.h):
 * lets tests/engines/test_signalsmith_schedule.py check the planner's
 * invariants directly, without going through the engine. Returns a list of
 * (input_offset, output_offset, input_count, output_count) dict chunks
 * plus tail_reserve/process_end_output/seek_len/last_rate. */
nb::dict plan_warp_schedule_py(MarkersBuffer markers, int64_t frames,
                                int64_t target_frames, int64_t seek_len,
                                int64_t interval) {
    std::vector<std::pair<int64_t, int64_t>> marker_pairs;
    size_t k = markers.shape(0);
    marker_pairs.reserve(k);
    for (size_t i = 0; i < k; ++i) {
        marker_pairs.emplace_back(markers(i, 0), markers(i, 1));
    }
    WarpSchedule plan =
        plan_warp_schedule(marker_pairs, frames, target_frames, seek_len, interval);

    nb::list chunks;
    for (const auto &c : plan.chunks) {
        nb::dict chunk;
        chunk["input_offset"] = c.input_offset;
        chunk["output_offset"] = c.output_offset;
        chunk["input_count"] = c.input_count;
        chunk["output_count"] = c.output_count;
        chunks.append(chunk);
    }

    nb::dict out;
    out["chunks"] = chunks;
    out["seek_len"] = plan.seek_len;
    out["tail_reserve"] = plan.tail_reserve;
    out["process_end_output"] = plan.process_end_output;
    out["last_rate"] = plan.last_rate;
    return out;
}

nb::dict engine_info() {
    // Smoke path: construct and configure one stretcher to prove the
    // single-file build actually links and runs, not merely compiles.
    SignalsmithStretch<float> stretch(kSeed);
    stretch.presetDefault(1, 44100.0f);

    std::ostringstream version;
    version << SignalsmithStretch<float>::version[0] << "."
            << SignalsmithStretch<float>::version[1] << "."
            << SignalsmithStretch<float>::version[2];

    // .c_str(): nanobind's nb::dict assigns via its built-in const char*
    // caster; a bare std::string needs <nanobind/stl/string.h> for its
    // caster, which is now also included above for the `quality` argument.
    std::string version_str = version.str();

    nb::dict info;
    info["engine"] = "signalsmith";
    info["version"] = version_str.c_str();
    info["source_revision"] = PYTIMESTRETCH_SS_SOURCE_REVISION;
    info["linear_revision"] = PYTIMESTRETCH_SS_LINEAR_REVISION;
    info["fft"] = PYTIMESTRETCH_SS_FFT;
    info["preset"] = "default";
    info["seed"] = static_cast<long long>(kSeed);
    return info;
}

}  // namespace

NB_MODULE(_signalsmith, m) {
    m.doc() = "Native Signalsmith Stretch binding: engine_info() and the render() native contract v2.";
    // Quality names Signalsmith can honor (no "fast" equivalent per the
    // plan); the single place that knows this engine's capability. The
    // facade (step 2) uses it to raise UnsupportedOptionError before
    // calling render() at all; configure_engine() also enforces it itself
    // (defense in depth).
    m.attr("SUPPORTED_QUALITY") = nb::make_tuple("high", "balanced");
    m.def("engine_info", &engine_info, "Report the compiled Signalsmith Stretch build configuration.");
    m.def("render", &render, nb::arg("buffer"), nb::arg("sample_rate"),
          nb::arg("markers"), nb::arg("pitch_scale"),
          nb::arg("preserve_formants"), nb::arg("quality"),
          "Render buffer (channels, frames) float32 to "
          "(channels, markers[-1][1]) float32 per native contract v2: "
          ".exact() for K == 2 markers, a scheduled process()/flush() "
          "stream for K > 2 (warp).");
    m.def("_stretch_diagnostics", &stretch_diagnostics, nb::arg("buffer"),
          nb::arg("sample_rate"), nb::arg("markers"), nb::arg("pitch_scale"),
          nb::arg("preserve_formants"), nb::arg("quality"),
          "Measurement-only: run the same pipeline as render() and report "
          "exact_ok/padded/padded_frames/input_latency/output_latency/"
          "block/interval/path instead of the audio itself.");
    m.def("_plan_warp_schedule", &plan_warp_schedule_py, nb::arg("markers"),
          nb::arg("frames"), nb::arg("target_frames"), nb::arg("seek_len"),
          nb::arg("interval"),
          "Test-only: expose signalsmith_schedule.h's plan_warp_schedule() "
          "so its invariants can be checked directly.");
}
