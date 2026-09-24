/**
 * rubberband_module.cpp — nanobind entry point for pytimestretch._rubberband.
 *
 * ★ Implements the native contract the facade (src/pytimestretch/stretch.py)
 * dispatches to: `stretch(buffer, sample_rate, duration_ratio,
 * target_frames) -> float32[channels, target_frames]`. `run_offline()` owns
 * the shared two-pass offline pipeline (study() then process()/retrieve()
 * in blocks, offline mode's internal start-delay/pad compensation, and
 * trim-or-zero-pad to the caller-computed exact length); `stretch()` and
 * `_stretch_diagnostics()` are thin callers of it so there is exactly one
 * place that knows the Rubber Band offline block loop. `time_ratio` is
 * derived from `target_frames / frames`, not from `duration_ratio` directly,
 * so the engine targets the facade's exact rounded length; `duration_ratio`
 * is kept only to build a clearer error message. `engine_info()` remains
 * from step 2.
 *
 * Reads: rubberband/RubberBandStretcher.h (vendored, extern/rubberband).
 */

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <sstream>
#include <stdexcept>
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
// call from a single worker thread per stretch() call).
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

/** Deinterleaved (per-channel) result of the offline pipeline, before the
 * caller trims or zero-pads it to target_frames, plus the diagnostics the
 * plan wants measured. */
struct OfflineResult {
    std::vector<std::vector<float>> channels;  // [channel][raw_frames]
    size_t start_delay = 0;
    size_t preferred_start_pad = 0;
    size_t block = 0;
};

/**
 * Run the shared two-pass Rubber Band offline pipeline (study, then
 * process + retrieve in blocks) over `input` and return every frame the
 * engine produced, undecided on trimming/padding — the two public
 * entry points below own that decision (stretch() trims/pads to
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

/** Validate the shared inputs to stretch()/_stretch_diagnostics() and
 * return (channels, frames). */
std::pair<size_t, size_t> validate(const InputBuffer &buffer,
                                    int sample_rate, double duration_ratio,
                                    long long target_frames) {
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
    if (!(duration_ratio > 0.0) || !std::isfinite(duration_ratio)) {
        std::ostringstream msg;
        msg << "rubberband: duration_ratio must be finite and > 0, got "
            << duration_ratio;
        throw std::runtime_error(msg.str());
    }
    if (target_frames < 1) {
        throw std::runtime_error("rubberband: target_frames must be >= 1, got " +
                                  std::to_string(target_frames));
    }
    return {channels, frames};
}

std::vector<const float *> channel_pointers(const InputBuffer &buffer,
                                             size_t channels, size_t frames) {
    std::vector<const float *> ptrs(channels);
    for (size_t c = 0; c < channels; ++c) {
        ptrs[c] = buffer.data() + c * frames;
    }
    return ptrs;
}

nb::ndarray<nb::numpy, float, nb::ndim<2>> stretch(InputBuffer buffer,
                                                     int sample_rate,
                                                     double duration_ratio,
                                                     long long target_frames) {
    auto [channels, frames] =
        validate(buffer, sample_rate, duration_ratio, target_frames);
    double time_ratio = static_cast<double>(target_frames) / static_cast<double>(frames);

    OfflineResult result;
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, channels, frames);
        nb::gil_scoped_release release;
        result = run_offline(in_ptrs, channels, frames,
                              static_cast<size_t>(sample_rate), time_ratio);
    }

    float *data = place_and_own(result.channels, channels, result.start_delay,
                                 static_cast<size_t>(target_frames));

    nb::capsule owner(data, [](void *p) noexcept { delete[] static_cast<float *>(p); });
    size_t shape[2] = {channels, static_cast<size_t>(target_frames)};
    return nb::ndarray<nb::numpy, float, nb::ndim<2>>(data, 2, shape, owner);
}

/** Measurement-only variant sharing run_offline(): reports raw_frames
 * (before trim/pad), start_delay, preferred_start_pad, and the block size
 * used, instead of the trimmed/padded audio itself. */
nb::dict stretch_diagnostics(InputBuffer buffer, int sample_rate,
                              long long target_frames) {
    // duration_ratio has no bearing on the diagnostics dict; pass a
    // trivially valid value through the shared validator.
    auto [channels, frames] = validate(buffer, sample_rate, 1.0, target_frames);
    double time_ratio = static_cast<double>(target_frames) / static_cast<double>(frames);

    OfflineResult result;
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, channels, frames);
        nb::gil_scoped_release release;
        result = run_offline(in_ptrs, channels, frames,
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
    m.doc() = "Native Rubber Band binding: engine_info() and the stretch() native contract.";
    m.def("engine_info", &engine_info, "Report the compiled Rubber Band build configuration.");
    m.def("stretch", &stretch, nb::arg("buffer"), nb::arg("sample_rate"),
          nb::arg("duration_ratio"), nb::arg("target_frames"),
          "Offline time-stretch buffer (channels, frames) float32 to "
          "(channels, target_frames) float32.");
    m.def("_stretch_diagnostics", &stretch_diagnostics, nb::arg("buffer"),
          nb::arg("sample_rate"), nb::arg("target_frames"),
          "Measurement-only: run the same pipeline as stretch() and report "
          "raw_frames/start_delay/preferred_start_pad/block instead of "
          "trimmed audio.");
}
