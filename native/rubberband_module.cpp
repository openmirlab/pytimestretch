/**
 * rubberband_module.cpp — nanobind entry point for pytimestretch._rubberband.
 *
 * ★ Implements native contract v2 in full: `render(buffer, sample_rate,
 * markers, pitch_scale, preserve_formants, quality) ->
 * float32[channels, markers[-1][1]]`, which the facade
 * (src/pytimestretch/stretch.py) dispatches to. `run_offline()` owns the
 * shared two-pass offline pipeline (study() then process()/retrieve() in
 * blocks, start-delay/pad compensation, trim-or-zero-pad to the exact
 * length); `render()` and `_stretch_diagnostics()` are thin callers of it
 * and of `validate_render()` (contract v2 checks plus this engine's own
 * quality/key-frame-map resolution), so each concern has exactly one owner.
 *
 * Reads: render_contract.h, rubberband/RubberBandStretcher.h (vendored,
 * extern/rubberband).
 */

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "render_contract.h"
#include "rubberband/RubberBandStretcher.h"

namespace nb = nanobind;
using RubberBand::RubberBandStretcher;
using pytimestretch::native::channel_pointers;
using pytimestretch::native::InputBuffer;
using pytimestretch::native::make_output;
using pytimestretch::native::MarkersBuffer;
using pytimestretch::native::validate_common;

#ifndef PYTIMESTRETCH_RB_FFT
#define PYTIMESTRETCH_RB_FFT "unknown"
#endif

#ifndef PYTIMESTRETCH_RB_SOURCE_REVISION
#define PYTIMESTRETCH_RB_SOURCE_REVISION "v4.0.0"
#endif

namespace {

// Decided engine setup (binding-first plan, step 3): offline mode, no
// internal threading (we already release the GIL and call from a single
// worker thread per render() call). The engine/window (quality) and
// formant options vary per call; see quality_options() and
// formant_option() below.
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
constexpr RubberBandStretcher::Options kBaseEngineOptions =
    RubberBandStretcher::OptionProcessOffline |
    RubberBandStretcher::OptionThreadingNever |
    RubberBandStretcher::OptionChannelsApart;

/** quality -> the engine/window options it selects, per the plan's step 3
 * decision: "high" = R3 standard window (current default); "balanced" = R3
 * + OptionWindowShort (faster, some quality cost per the header). "fast"
 * (R2/OptionEngineFaster) was removed 2026-09-25: blind listening round 2
 * found no audible benefit and no real speed edge over "balanced". Any
 * other string is a genuine bad call, not an unimplemented feature --
 * std::invalid_argument, same family as an unknown formants/markers value
 * would be if this binding validated those itself. */
RubberBandStretcher::Options quality_options(const std::string &quality) {
    if (quality == "high") {
        return RubberBandStretcher::OptionEngineFiner;
    }
    if (quality == "balanced") {
        return RubberBandStretcher::OptionEngineFiner |
               RubberBandStretcher::OptionWindowShort;
    }
    throw std::invalid_argument(
        "rubberband: quality \"" + quality +
        "\" is not one of \"high\", \"balanced\"");
}

/** Deinterleaved (per-channel) result of the offline pipeline, before the
 * caller trims or zero-pads it to target_frames, plus the diagnostics the
 * plan wants measured. */
struct OfflineResult {
    std::vector<std::vector<float>> channels;  // [channel][raw_frames]
    size_t start_delay = 0;
    size_t preferred_start_pad = 0;
    size_t block = 0;
    int engine_version = 0;
};

/** Contract v2 inputs, resolved and validated by validate_render(). */
struct RenderInputs {
    size_t channels;
    size_t frames;
    size_t target_frames;
    RubberBandStretcher::Options options;
    std::map<size_t, size_t> key_frame_map;  // empty when markers has K == 2
    bool has_key_frame_map = false;
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
                           double time_ratio, double pitch_scale,
                           RubberBandStretcher::Options options,
                           const std::map<size_t, size_t> *key_frame_map) {
    RubberBandStretcher stretcher(sample_rate, channels, options, time_ratio,
                                   pitch_scale);
    int engine_version = stretcher.getEngineVersion();

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

    // Per the header: the time/pitch ratios (both already set via the
    // constructor above) must be set before setKeyFrameMap(), and the map
    // must be set before the first study()/process() call.
    if (key_frame_map != nullptr) {
        stretcher.setKeyFrameMap(*key_frame_map);
    }

    OfflineResult result;
    result.block = block;
    result.engine_version = engine_version;
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
 * exactly `target_frames`, writing into `data`, an already-allocated
 * C-contiguous float32 (channels, target_frames) buffer (from
 * render_contract.h's make_output()). */
void place_into(float *data, const std::vector<std::vector<float>> &raw,
                 size_t channels, size_t start_delay, size_t target_frames) {
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
}

/**
 * Validate the shared inputs to render()/_stretch_diagnostics() and return
 * (channels, frames, target_frames, options, key_frame_map). Derives frames
 * from the buffer itself and target_frames from `markers[-1][1]`, checking
 * `markers[-1][0]` against the buffer's own frame count rather than
 * trusting it. Resolves `quality` to engine/window options (raising
 * `std::invalid_argument` for an unknown name, matching how an unknown
 * `formants`/`markers` value would be a bad call rather than an
 * unimplemented feature) and ORs in the formant option. For `K > 2`
 * markers, builds the key-frame map from every row; `K == 2` leaves it
 * empty (the original two-marker path, no map).
 */
RenderInputs validate_render(const InputBuffer &buffer, int sample_rate,
                              const MarkersBuffer &markers, double pitch_scale,
                              bool preserve_formants,
                              const std::string &quality) {
    auto common =
        validate_common(buffer, sample_rate, markers, pitch_scale, "rubberband");
    size_t k = markers.shape(0);

    RubberBandStretcher::Options options =
        kBaseEngineOptions | quality_options(quality) |
        (preserve_formants ? RubberBandStretcher::OptionFormantPreserved
                            : RubberBandStretcher::OptionFormantShifted);

    RenderInputs in;
    in.channels = common.channels;
    in.frames = common.frames;
    in.target_frames = common.target_frames;
    in.options = options;
    // Including the leading (0, 0) row in the
    // key-frame map is a genuine R3Stretcher::updateRatioFromMap() bug, not
    // a caller mistake -- with m_consumedInputDuration == 0 it computes the
    // initial ratio as map.begin()->second / map.begin()->first, i.e. 0/0,
    // which is NaN and triggers RubberBand's own "NaN or Inf presented"
    // warning (silently resetting the ratio to 1.0, no stretch at all,
    // for the whole render). The trailing (frames, target_frames) row is
    // safe to include (verified no such reset). So the map is built from
    // every row except the first: rows 1..k-1, which are still "every
    // marker but the always-(0,0) start."
    in.has_key_frame_map = (k > 2);
    if (in.has_key_frame_map) {
        for (size_t i = 1; i < k; ++i) {
            int64_t source = markers(i, 0);
            int64_t target = markers(i, 1);
            in.key_frame_map[static_cast<size_t>(source)] =
                static_cast<size_t>(target);
        }
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
    double time_ratio = static_cast<double>(in.target_frames) /
                         static_cast<double>(in.frames);

    OfflineResult result;
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, in.channels, in.frames);
        const std::map<size_t, size_t> *key_frame_map =
            in.has_key_frame_map ? &in.key_frame_map : nullptr;
        nb::gil_scoped_release release;
        result = run_offline(in_ptrs, in.channels, in.frames,
                              static_cast<size_t>(sample_rate), time_ratio,
                              pitch_scale, in.options, key_frame_map);
    }

    auto out = make_output(in.channels, in.target_frames);
    place_into(out.data(), result.channels, in.channels, result.start_delay,
               in.target_frames);
    return out;
}

/** Measurement-only variant sharing run_offline() and validate_render():
 * reports raw_frames (before trim/pad), start_delay, preferred_start_pad,
 * the block size used, and the engine_version actually constructed (always
 * 3 for "high"/"balanced"/R3), instead of the trimmed/padded audio itself. */
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
        const std::map<size_t, size_t> *key_frame_map =
            in.has_key_frame_map ? &in.key_frame_map : nullptr;
        nb::gil_scoped_release release;
        result = run_offline(in_ptrs, in.channels, in.frames,
                              static_cast<size_t>(sample_rate), time_ratio,
                              pitch_scale, in.options, key_frame_map);
    }

    size_t raw_frames = result.channels.empty() ? 0 : result.channels[0].size();
    nb::dict info;
    info["raw_frames"] = raw_frames;
    info["start_delay"] = result.start_delay;
    info["preferred_start_pad"] = result.preferred_start_pad;
    info["block"] = result.block;
    info["engine_version"] = result.engine_version;
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
    // Quality names Rubber Band can honor; the single place that knows this
    // engine's capability. The facade (step 2) uses it to raise
    // UnsupportedOptionError before calling render() at all.
    m.attr("SUPPORTED_QUALITY") = nb::make_tuple("high", "balanced");
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
