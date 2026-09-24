/**
 * rubberband_module.cpp — nanobind entry point for pytimestretch._rubberband.
 *
 * ★ Implements native contract v2, which the facade
 * (src/pytimestretch/stretch.py) dispatches to: `render(buffer, sample_rate,
 * markers, pitch_scale, preserve_formants, quality) ->
 * float32[channels, markers[-1][1]]`. `markers` is an int64 `(K, 2)` array
 * of `(source_frame, output_frame)` pairs; `frames` is read from
 * `markers[-1][0]` (and checked against the buffer's own frame count) and
 * `target_frames` from `markers[-1][1]`, rather than being passed
 * separately, so there is exactly one source of truth for both. This step
 * (native contract v2, behavior-preserving) implements only the plain
 * two-marker path with no pitch/formant/quality change — the same offline
 * pipeline `stretch()` ran before — and raises `std::invalid_argument` for
 * every other combination (K > 2 markers, `pitch_scale != 1.0`,
 * `preserve_formants`, `quality != "high"`) as a deliberate "not
 * implemented yet" for steps 3/4 to fill in, not a validation failure.
 * `run_offline()` still owns the shared two-pass offline pipeline (study()
 * then process()/retrieve() in blocks, offline mode's internal
 * start-delay/pad compensation, and trim-or-zero-pad to the caller-computed
 * exact length); `render()` and `_stretch_diagnostics()` are thin callers
 * of it, sharing `validate_render()` for the contract v2 input checks, so
 * there is exactly one place that knows the Rubber Band offline block loop
 * and exactly one place that knows contract v2 validation.
 * `SUPPORTED_QUALITY` names the quality presets Rubber Band can honor once
 * complete ("high"/"balanced"/"fast"); this step does not yet implement
 * "balanced"/"fast", so `render()` still rejects them, same as any other
 * unimplemented option. `engine_info()` remains from step 2.
 *
 * Reads: rubberband/RubberBandStretcher.h (vendored, extern/rubberband).
 */

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "rubberband/RubberBandStretcher.h"

namespace nb = nanobind;
using RubberBand::RubberBandStretcher;

#ifndef PYTIMESTRETCH_RB_FFT
#define PYTIMESTRETCH_RB_FFT "unknown"
#endif

#ifndef PYTIMESTRETCH_RB_SOURCE_REVISION
#define PYTIMESTRETCH_RB_SOURCE_REVISION "v4.0.0"
#endif

namespace {

// Decided engine setup (binding-first plan, step 3): offline mode, R3
// (Finer) engine, no internal threading (we already release the GIL and
// call from a single worker thread per render() call).
//
// OptionChannelsApart, NOT the plan's originally proposed
// OptionChannelsTogether: measured (tests/engines/test_rubberband.py,
// stereo-crosstalk case) with OptionChannelsTogether a fully silent
// channel against a noisy other channel picked up energy up to ~0.71
// peak / ~-15 dBFS RMS — real R3 mid/side-style coupling from that
// option's own documented "aim to maximise clarity at the centre" behavior,
// not a bug here. That breaks the contract suite's channel-independence
// guarantee (tests/contract/test_contract.py::test_stereo_channel_order_preserved),
// which is a harder invariant than the plan's "my call" default. Verified
// OptionChannelsApart gives bit-exact 0.0 crosstalk on the same input.
// Report this deviation from the plan back to Paul; revisit only by his
// decision.
constexpr RubberBandStretcher::Options kEngineOptions =
    RubberBandStretcher::OptionProcessOffline |
    RubberBandStretcher::OptionEngineFiner |
    RubberBandStretcher::OptionThreadingNever |
    RubberBandStretcher::OptionChannelsApart;

using InputBuffer =
    nb::ndarray<const float, nb::ndim<2>, nb::c_contig, nb::device::cpu>;

// Native contract v2's marker array: int64 (K, 2) rows of
// (source_frame, output_frame), C-contiguous. The facade guarantees the
// invariants (first row (0, 0), last row (frames, target), both columns
// strictly increasing, K >= 2); this binding re-derives frames/target from
// the last row and still checks frames against the buffer, rather than
// trusting the facade blindly.
using MarkersBuffer =
    nb::ndarray<const int64_t, nb::shape<-1, 2>, nb::c_contig, nb::device::cpu>;

/** Deinterleaved (per-channel) result of the offline pipeline, before the
 * caller trims or zero-pads it to target_frames, plus the diagnostics the
 * plan wants measured. */
struct OfflineResult {
    std::vector<std::vector<float>> channels;  // [channel][raw_frames]
    size_t start_delay = 0;
    size_t preferred_start_pad = 0;
    size_t block = 0;
};

/** Contract v2 inputs, resolved and validated by validate_render(). */
struct RenderInputs {
    size_t channels;
    size_t frames;
    size_t target_frames;
};

/**
 * Run the shared two-pass Rubber Band offline pipeline (study, then
 * process + retrieve in blocks) over `input` and return every frame the
 * engine produced, undecided on trimming/padding — the two public
 * entry points below own that decision (render() trims/pads to
 * target_frames; _stretch_diagnostics() reports raw_frames instead).
 *
 * `input[c]` must point to `frames` contiguous samples for channel `c`.
 * Runs with the GIL released by the caller; touches no Python state.
 */
OfflineResult run_offline(const std::vector<const float *> &input,
                           size_t channels, size_t frames, size_t sample_rate,
                           double time_ratio) {
    RubberBandStretcher stretcher(sample_rate, channels, kEngineOptions,
                                   time_ratio, /*initialPitchScale=*/1.0);

    // A block size the header explicitly recommends bounding by
    // getProcessSizeLimit() (524288 as of v3.3); 4096 is a plain,
    // conservative per-call chunk well under that limit and under typical
    // input lengths, so almost every real call still loops more than once
    // (exercising the block loop, not just a single big call).
    size_t block = std::min<size_t>(stretcher.getProcessSizeLimit(), 4096);
    if (block == 0) {
        throw std::runtime_error(
            "rubberband: getProcessSizeLimit() returned 0");
    }

    stretcher.setExpectedInputDuration(frames);
    stretcher.setMaxProcessSize(block);

    OfflineResult result;
    result.block = block;
    result.channels.assign(channels, {});

    std::vector<const float *> in_ptrs(channels);

    // Pass 1: study() over the whole input in blocks, final=true on the
    // last block, per the header's offline contract.
    {
        size_t pos = 0;
        do {
            size_t n = std::min(block, frames - pos);
            for (size_t c = 0; c < channels; ++c) {
                in_ptrs[c] = input[c] + pos;
            }
            bool final_block = (pos + n >= frames);
            stretcher.study(in_ptrs.data(), n, final_block);
            pos += n;
        } while (pos < frames);
    }

    result.preferred_start_pad = stretcher.getPreferredStartPad();

    // Pass 2: process() in blocks, final=true on the last, draining every
    // available() frame after each call via retrieve().
    std::vector<float> retrieve_buf(channels * block);
    std::vector<float *> retrieve_ptrs(channels);
    for (size_t c = 0; c < channels; ++c) {
        retrieve_ptrs[c] = retrieve_buf.data() + c * block;
    }

    bool finished = false;
    auto drain = [&]() {
        while (!finished) {
            int avail = stretcher.available();
            if (avail == -1) {
                finished = true;
                break;
            }
            if (avail <= 0) {
                break;
            }
            size_t want = std::min<size_t>(static_cast<size_t>(avail), block);
            size_t got = stretcher.retrieve(retrieve_ptrs.data(), want);
            if (got == 0) {
                break;
            }
            for (size_t c = 0; c < channels; ++c) {
                result.channels[c].insert(result.channels[c].end(),
                                           retrieve_ptrs[c],
                                           retrieve_ptrs[c] + got);
            }
        }
    };

    {
        size_t pos = 0;
        do {
            size_t n = std::min(block, frames - pos);
            for (size_t c = 0; c < channels; ++c) {
                in_ptrs[c] = input[c] + pos;
            }
            bool final_block = (pos + n >= frames);
            stretcher.process(in_ptrs.data(), n, final_block);
            pos += n;
            drain();
        } while (pos < frames);
    }

    // Offline processing here is fully synchronous (OptionThreadingNever,
    // no worker thread), so the final process() call above should already
    // have produced everything; this loop only exists to read out any
    // remaining available() frames and observe the -1 "finished" signal.
    // Bounded so a Rubber Band anomaly raises instead of hanging.
    int guard = 0;
    while (!finished) {
        drain();
        if (finished) {
            break;
        }
        if (++guard > 1'000'000) {
            throw std::runtime_error(
                "rubberband: offline processing did not terminate "
                "(available() never returned -1 after final process())");
        }
    }

    result.start_delay = stretcher.getStartDelay();
    return result;
}

/** Trim or zero-pad `raw[c]` (after dropping `start_delay` leading frames,
 * if any — offline mode documents this as always 0, but the plan asks the
 * code to compensate any remaining delay rather than assume the doc) to
 * exactly `target_frames`, writing into a freshly allocated, owned,
 * C-contiguous float32 (channels, target_frames) buffer. */
float *place_and_own(const std::vector<std::vector<float>> &raw,
                      size_t channels, size_t start_delay,
                      size_t target_frames) {
    float *data = new float[channels * target_frames];
    for (size_t c = 0; c < channels; ++c) {
        const std::vector<float> &src = raw[c];
        size_t available_after_delay =
            src.size() > start_delay ? src.size() - start_delay : 0;
        size_t copy_n = std::min(available_after_delay, target_frames);
        float *dst = data + c * target_frames;
        if (copy_n > 0) {
            std::memcpy(dst, src.data() + start_delay, copy_n * sizeof(float));
        }
        if (copy_n < target_frames) {
            std::memset(dst + copy_n, 0, (target_frames - copy_n) * sizeof(float));
        }
    }
    return data;
}

/**
 * Validate the shared inputs to render()/_stretch_diagnostics() and return
 * (channels, frames, target_frames). Derives frames from the buffer itself
 * and target_frames from `markers[-1][1]`, checking `markers[-1][0]` against
 * the buffer's own frame count rather than trusting it. Then enforces this
 * step's behavior-preserving scope: raises `std::invalid_argument` (->
 * Python ValueError) for any marker/pitch/formant/quality combination this
 * step does not implement yet, so a caller sees a deliberate "not
 * implemented" rather than either silently ignoring the option or a
 * validation-shaped error.
 */
RenderInputs validate_render(const InputBuffer &buffer, int sample_rate,
                              const MarkersBuffer &markers, double pitch_scale,
                              bool preserve_formants,
                              const std::string &quality) {
    size_t channels = buffer.shape(0);
    size_t frames = buffer.shape(1);
    if (channels < 1 || frames < 1) {
        throw std::runtime_error(
            "rubberband: buffer must have at least one channel and frame, "
            "got shape (" +
            std::to_string(channels) + ", " + std::to_string(frames) + ")");
    }
    if (sample_rate <= 0) {
        throw std::runtime_error("rubberband: sample_rate must be > 0, got " +
                                  std::to_string(sample_rate));
    }

    size_t k = markers.shape(0);
    if (k < 2) {
        throw std::runtime_error(
            "rubberband: markers must have at least 2 rows, got " +
            std::to_string(k));
    }

    int64_t marker_frames = markers(k - 1, 0);
    int64_t marker_target = markers(k - 1, 1);
    if (marker_frames < 0 || static_cast<size_t>(marker_frames) != frames) {
        throw std::runtime_error(
            "rubberband: markers[-1][0] (" + std::to_string(marker_frames) +
            ") must equal the buffer's frame count (" +
            std::to_string(frames) + ")");
    }
    if (marker_target < 1) {
        throw std::runtime_error(
            "rubberband: markers[-1][1] must be >= 1, got " +
            std::to_string(marker_target));
    }

    // Behavior-preserving scope for this step: only the plain two-marker,
    // no-pitch, no-formant, "high"-quality path runs the pipeline below.
    // Steps 3/4 implement the rest; every other combination is a genuine
    // unimplemented feature, not a bad call, so it raises invalid_argument
    // rather than runtime_error.
    if (k != 2) {
        throw std::invalid_argument(
            "rubberband: markers with more than two entries (warp) not "
            "implemented yet");
    }
    if (pitch_scale != 1.0) {
        throw std::invalid_argument(
            "rubberband: pitch_scale != 1.0 not implemented yet");
    }
    if (preserve_formants) {
        throw std::invalid_argument(
            "rubberband: preserve_formants not implemented yet");
    }
    if (quality != "high") {
        throw std::invalid_argument("rubberband: quality \"" + quality +
                                     "\" not implemented yet");
    }

    return {channels, frames, static_cast<size_t>(marker_target)};
}

std::vector<const float *> channel_pointers(const InputBuffer &buffer,
                                             size_t channels, size_t frames) {
    std::vector<const float *> ptrs(channels);
    for (size_t c = 0; c < channels; ++c) {
        ptrs[c] = buffer.data() + c * frames;
    }
    return ptrs;
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
    double time_ratio = static_cast<double>(in.target_frames) /
                         static_cast<double>(in.frames);

    OfflineResult result;
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, in.channels, in.frames);
        nb::gil_scoped_release release;
        result = run_offline(in_ptrs, in.channels, in.frames,
                              static_cast<size_t>(sample_rate), time_ratio);
    }

    float *data = place_and_own(result.channels, in.channels,
                                 result.start_delay, in.target_frames);

    nb::capsule owner(data, [](void *p) noexcept { delete[] static_cast<float *>(p); });
    size_t shape[2] = {in.channels, in.target_frames};
    return nb::ndarray<nb::numpy, float, nb::ndim<2>>(data, 2, shape, owner);
}

/** Measurement-only variant sharing run_offline() and validate_render():
 * reports raw_frames (before trim/pad), start_delay, preferred_start_pad,
 * and the block size used, instead of the trimmed/padded audio itself. */
nb::dict stretch_diagnostics(InputBuffer buffer, int sample_rate,
                              MarkersBuffer markers, double pitch_scale,
                              bool preserve_formants, std::string quality) {
    RenderInputs in = validate_render(buffer, sample_rate, markers,
                                       pitch_scale, preserve_formants,
                                       quality);
    double time_ratio = static_cast<double>(in.target_frames) /
                         static_cast<double>(in.frames);

    OfflineResult result;
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, in.channels, in.frames);
        nb::gil_scoped_release release;
        result = run_offline(in_ptrs, in.channels, in.frames,
                              static_cast<size_t>(sample_rate), time_ratio);
    }

    size_t raw_frames = result.channels.empty() ? 0 : result.channels[0].size();
    nb::dict info;
    info["raw_frames"] = raw_frames;
    info["start_delay"] = result.start_delay;
    info["preferred_start_pad"] = result.preferred_start_pad;
    info["block"] = result.block;
    return info;
}

nb::dict engine_info() {
    // Smoke path: construct and tear down one offline, R3 (Finer) stretcher
    // to prove the single-file build actually links and runs, not merely
    // compiles. Values below feed into the reported dict rather than being
    // discarded, so this is verification, not a throwaway side effect.
    RubberBandStretcher stretcher(
        44100,
        1,
        RubberBandStretcher::OptionProcessOffline
            | RubberBandStretcher::OptionEngineFiner
            | RubberBandStretcher::OptionThreadingNever);
    int engine_version = stretcher.getEngineVersion();

    nb::dict info;
    info["engine"] = "rubberband";
    info["version"] = RUBBERBAND_VERSION;
    info["engine_version"] = engine_version;
    info["fft"] = PYTIMESTRETCH_RB_FFT;
    info["resampler"] = "bqresampler";
    info["source_revision"] = PYTIMESTRETCH_RB_SOURCE_REVISION;
    return info;
}

}  // namespace

NB_MODULE(_rubberband, m) {
    m.doc() = "Native Rubber Band binding: engine_info() and the render() native contract v2.";
    // Quality names Rubber Band can honor once steps 3/4 land; the single
    // place that knows this engine's capability. The facade (step 2) uses
    // it to raise UnsupportedOptionError; this step does not gate on it
    // itself (validate_render() rejects every quality but "high" outright).
    m.attr("SUPPORTED_QUALITY") = nb::make_tuple("high", "balanced", "fast");
    m.def("engine_info", &engine_info, "Report the compiled Rubber Band build configuration.");
    m.def("render", &render, nb::arg("buffer"), nb::arg("sample_rate"),
          nb::arg("markers"), nb::arg("pitch_scale"),
          nb::arg("preserve_formants"), nb::arg("quality"),
          "Offline render buffer (channels, frames) float32 to "
          "(channels, markers[-1][1]) float32 per native contract v2.");
    m.def("_stretch_diagnostics", &stretch_diagnostics, nb::arg("buffer"),
          nb::arg("sample_rate"), nb::arg("markers"), nb::arg("pitch_scale"),
          nb::arg("preserve_formants"), nb::arg("quality"),
          "Measurement-only: run the same pipeline as render() and report "
          "raw_frames/start_delay/preferred_start_pad/block instead of "
          "trimmed audio.");
}
