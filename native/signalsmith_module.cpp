/**
 * signalsmith_module.cpp — nanobind entry point for pytimestretch._signalsmith.
 *
 * ★ Implements the same native contract as native/rubberband_module.cpp:
 * `stretch(buffer, sample_rate, duration_ratio, target_frames) ->
 * float32[channels, target_frames]`, capsule-owned, GIL released during
 * engine work, `std::runtime_error` on anomalies. `run_signalsmith()` is the
 * one place that knows the Signalsmith Stretch pipeline (construct with a
 * fixed seed, `presetDefault()`, `.exact()` whole-buffer processing).
 * `.exact()` already produces exactly the requested output length by
 * itself, unlike Rubber Band's two-pass offline loop — except when the
 * input is shorter than its internal seek/pre-roll requirement, in which
 * case it zero-fills instead of stretching; `run_signalsmith()` zero-pads
 * the input up past that threshold (scaling the output length to match,
 * then trimming back to the caller's `target_frames`) so ordinary short
 * clips still get real output, not silence; any remaining `.exact()`
 * failure raises instead of returning its zero-fill.
 * `stretch()` and `_stretch_diagnostics()` are thin callers of it.
 *
 * Reads: signalsmith-stretch/signalsmith-stretch.h (vendored, extern/signalsmith-stretch).
 */

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

// signalsmith-linear/fft.h calls std::memcpy without including <cstring>
// itself (known upstream gap, not patched here — see CLAUDE.md's vendoring
// policy); include it first so the vendored headers below compile.
#include <cstring>

#include <cmath>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <vector>

#include "signalsmith-stretch/signalsmith-stretch.h"

namespace nb = nanobind;
using signalsmith::stretch::SignalsmithStretch;

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

// Decided engine setup (binding-first plan, step 4): presetDefault (the
// library's documented default block/interval sizing), no split
// computation (that flag trades latency for spreading each block's work
// across more process() calls — irrelevant to a single whole-buffer
// .exact() call), no transpose/formant options (pitch stays unchanged,
// out of scope per the plan). A fixed seed makes the phase-randomization
// used internally for transient/peak handling deterministic across runs,
// which the contract suite's determinism test requires; 0x5eed is an
// arbitrary but memorable constant, not a tuned value.
constexpr long kSeed = 0x5eed;

using InputBuffer =
    nb::ndarray<const float, nb::ndim<2>, nb::c_contig, nb::device::cpu>;

/** Channel-indexable adapter over raw pointers, satisfying the `Inputs`/
 * `Outputs` template concept `.exact()` expects: `buffer[channel][index]`.
 * `operator[]` returns a raw pointer, which already supports `[index]`. */
template <typename T>
struct ChannelPointers {
    std::vector<T *> ptrs;
    T *operator[](int c) const { return ptrs[static_cast<size_t>(c)]; }
};

struct StretchDiagnostics {
    bool exact_ok = false;
    bool padded = false;
    int input_latency = 0;
    int output_latency = 0;
    int block_samples = 0;
    int interval_samples = 0;
    size_t padded_frames = 0;
};

/**
 * Run the Signalsmith Stretch whole-buffer pipeline: construct with
 * `kSeed`, configure via `presetDefault`, and call `.exact()`.
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
 * minimum, not on every call. Measured: even 1-frame and 10-frame inputs
 * complete with `exact_ok = true` after padding. If `.exact()` still
 * reports failure, `stretch()` raises rather than returning its zero-fill,
 * so the binding never passes silence off as a stretch.
 *
 * `output_data` must already be sized `channels * target_frames`,
 * C-contiguous, per-channel stride `target_frames`.
 *
 * Runs with the GIL released by the caller; touches no Python state.
 */
StretchDiagnostics run_signalsmith(const std::vector<const float *> &input,
                                    size_t channels, size_t frames,
                                    size_t sample_rate, size_t target_frames,
                                    float *output_data) {
    SignalsmithStretch<float> stretch(kSeed);
    stretch.presetDefault(static_cast<int>(channels),
                           static_cast<float>(sample_rate));

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

    if (seek_length > 0 &&
        frames < static_cast<size_t>(seek_length)) {
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

/** Validate the shared inputs to stretch()/_stretch_diagnostics() and
 * return (channels, frames). Mirrors native/rubberband_module.cpp's
 * validate() (each native module owns its own contract validation; the
 * two bindings intentionally do not share a header for this). */
std::pair<size_t, size_t> validate(const InputBuffer &buffer,
                                    int sample_rate, double duration_ratio,
                                    long long target_frames) {
    size_t channels = buffer.shape(0);
    size_t frames = buffer.shape(1);
    if (channels < 1 || frames < 1) {
        throw std::runtime_error(
            "signalsmith: buffer must have at least one channel and frame, "
            "got shape (" +
            std::to_string(channels) + ", " + std::to_string(frames) + ")");
    }
    if (sample_rate <= 0) {
        throw std::runtime_error("signalsmith: sample_rate must be > 0, got " +
                                  std::to_string(sample_rate));
    }
    if (!(duration_ratio > 0.0) || !std::isfinite(duration_ratio)) {
        std::ostringstream msg;
        msg << "signalsmith: duration_ratio must be finite and > 0, got "
            << duration_ratio;
        throw std::runtime_error(msg.str());
    }
    if (target_frames < 1) {
        throw std::runtime_error(
            "signalsmith: target_frames must be >= 1, got " +
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

    float *data = new float[channels * static_cast<size_t>(target_frames)];
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, channels, frames);
        StretchDiagnostics diag;
        {
            nb::gil_scoped_release release;
            diag = run_signalsmith(in_ptrs, channels, frames,
                                   static_cast<size_t>(sample_rate),
                                   static_cast<size_t>(target_frames), data);
        }
        if (!diag.exact_ok) {
            delete[] data;
            throw std::runtime_error(
                "signalsmith: exact() could not process " +
                std::to_string(frames) + " input frames into " +
                std::to_string(target_frames) +
                " output frames (padded to " +
                std::to_string(diag.padded_frames) + ")");
        }
    }

    nb::capsule owner(data, [](void *p) noexcept { delete[] static_cast<float *>(p); });
    size_t shape[2] = {channels, static_cast<size_t>(target_frames)};
    return nb::ndarray<nb::numpy, float, nb::ndim<2>>(data, 2, shape, owner);
}

/** Measurement-only variant sharing run_signalsmith(): reports whether
 * .exact() ran its full pipeline or hit the too-short-input zero-fill
 * path, plus the engine's input/output latency and block/interval sizes,
 * instead of the audio itself. */
nb::dict stretch_diagnostics(InputBuffer buffer, int sample_rate,
                              long long target_frames) {
    // duration_ratio has no bearing on the diagnostics dict; pass a
    // trivially valid value through the shared validator.
    auto [channels, frames] = validate(buffer, sample_rate, 1.0, target_frames);

    std::vector<float> scratch(channels * static_cast<size_t>(target_frames));
    StretchDiagnostics diag;
    {
        std::vector<const float *> in_ptrs =
            channel_pointers(buffer, channels, frames);
        nb::gil_scoped_release release;
        diag = run_signalsmith(in_ptrs, channels, frames,
                                static_cast<size_t>(sample_rate),
                                static_cast<size_t>(target_frames),
                                scratch.data());
    }

    nb::dict info;
    info["exact_ok"] = diag.exact_ok;
    info["padded"] = diag.padded;
    info["padded_frames"] = diag.padded_frames;
    info["input_latency"] = diag.input_latency;
    info["output_latency"] = diag.output_latency;
    info["block"] = diag.block_samples;
    info["interval"] = diag.interval_samples;
    return info;
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
    // caster, which this translation unit doesn't otherwise need.
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
    m.doc() = "Native Signalsmith Stretch binding: engine_info() and the stretch() native contract.";
    m.def("engine_info", &engine_info, "Report the compiled Signalsmith Stretch build configuration.");
    m.def("stretch", &stretch, nb::arg("buffer"), nb::arg("sample_rate"),
          nb::arg("duration_ratio"), nb::arg("target_frames"),
          "Whole-buffer time-stretch buffer (channels, frames) float32 to "
          "(channels, target_frames) float32 via .exact().");
    m.def("_stretch_diagnostics", &stretch_diagnostics, nb::arg("buffer"),
          nb::arg("sample_rate"), nb::arg("target_frames"),
          "Measurement-only: run the same pipeline as stretch() and report "
          "exact_ok/padded/padded_frames/input_latency/output_latency/"
          "block/interval instead of the audio itself.");
}
