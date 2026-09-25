/**
 * paulstretch_module.cpp — direct nanobind adapter for libpaulstretch.
 *
 * This is a separate creative operation, not native contract v2: its
 * duration ratio is passed through unchanged and output length is whatever
 * upstream's complete-FFT-chunk offline renderer produces. The Python
 * facade owns user validation and dtype/layout restoration; this module
 * checks the native boundary and reports its pinned build configuration.
 *
 * Reads: render_contract.h, paulstretch/paulstretch.h (vendored v0.3.0).
 */

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <utility>
#include <vector>

#include "paulstretch/paulstretch.h"
#include "render_contract.h"

namespace nb = nanobind;
using pytimestretch::native::InputBuffer;
using pytimestretch::native::make_output;

#ifndef PYTIMESTRETCH_PAULSTRETCH_SOURCE_REVISION
#define PYTIMESTRETCH_PAULSTRETCH_SOURCE_REVISION "v0.3.0"
#endif

namespace {

constexpr size_t kFftSize = 4096;
constexpr size_t kMinInputFrames = 20 * kFftSize;
// Upstream FFT construction advances a process-global non-atomic seed.
// Keep concurrent calls from racing while still releasing Python's GIL.
std::mutex render_mutex;

nb::ndarray<nb::numpy, float, nb::ndim<2>> render(
    InputBuffer buffer, int sample_rate, double duration_ratio) {
    const size_t channels = buffer.shape(0);
    const size_t frames = buffer.shape(1);
    if (channels < 1 || channels > 2) {
        throw std::invalid_argument("paulstretch: only mono and stereo audio are supported");
    }
    if (frames < kMinInputFrames) {
        throw std::invalid_argument("paulstretch: input needs at least 81920 frames");
    }
    if (sample_rate <= 0) {
        throw std::invalid_argument("paulstretch: sample_rate must be > 0");
    }
    if (!std::isfinite(duration_ratio) || duration_ratio < 1.0 ||
        duration_ratio > static_cast<double>(std::numeric_limits<float>::max())) {
        throw std::invalid_argument("paulstretch: duration_ratio must be finite and >= 1");
    }

    const float ratio = static_cast<float>(duration_ratio);
    const long double estimated_frames =
        std::ceil(static_cast<long double>(frames) * ratio) + kFftSize;
    if (estimated_frames >
        static_cast<long double>(std::numeric_limits<size_t>::max() / channels / sizeof(float))) {
        throw std::overflow_error("paulstretch: output would be too large");
    }

    paulstretch::RenderOptions options;
    options.stretch = ratio;
    options.fft_size = static_cast<int>(kFftSize);
    options.sample_rate = static_cast<float>(sample_rate);
    options.onset_detection_sensitivity = 0.0f;

    std::vector<float> left;
    std::vector<float> right;
    {
        nb::gil_scoped_release release;
        std::lock_guard<std::mutex> lock(render_mutex);
        paulstretch::OfflineRenderer renderer(options);
        const float *input = buffer.data();
        left.assign(input, input + frames);
        if (channels == 1) {
            left = renderer.render_mono(left);
        } else {
            right.assign(input + frames, input + 2 * frames);
            auto stereo = renderer.render_stereo(left, right);
            left = std::move(stereo.left);
            right = std::move(stereo.right);
        }
    }

    const size_t output_frames = left.size();
    if (output_frames == 0 || (channels == 2 && right.size() != output_frames) ||
        output_frames > std::numeric_limits<size_t>::max() / channels) {
        throw std::runtime_error("paulstretch: invalid output frame count");
    }
    if (!std::all_of(left.begin(), left.end(), [](float x) { return std::isfinite(x); }) ||
        (channels == 2 && !std::all_of(right.begin(), right.end(),
                                       [](float x) { return std::isfinite(x); }))) {
        throw std::runtime_error("paulstretch: output contains NaN or infinity");
    }

    auto out = make_output(channels, output_frames);
    std::copy(left.begin(), left.end(), out.data());
    if (channels == 2) {
        std::copy(right.begin(), right.end(), out.data() + output_frames);
    }
    return out;
}

nb::dict engine_info() {
    nb::dict info;
    info["engine"] = "libpaulstretch";
    info["version"] = "0.3.0";
    info["source_revision"] = PYTIMESTRETCH_PAULSTRETCH_SOURCE_REVISION;
    info["fft"] = paulstretch::fft_backend_name();
    info["fft_size"] = kFftSize;
    info["min_input_frames"] = kMinInputFrames;
    info["onset_detection"] = false;
    return info;
}

}  // namespace

NB_MODULE(_paulstretch, m) {
    m.doc() = "Native libpaulstretch binding for approximate-duration extreme stretching.";
    m.def("render", &render, nb::arg("buffer"), nb::arg("sample_rate"),
          nb::arg("duration_ratio"),
          "Render mono/stereo channels-first float32 audio without length compensation.");
    m.def("engine_info", &engine_info, "Report the compiled libpaulstretch build.");
}
