/**
 * bungee_module.cpp — offline position-curve adapter for Bungee Basic.
 *
 * A continuous output-time -> input-position curve drives the granular API.
 * This is separate from the forward-only native render contract v2. The
 * Python facade validates the public contract and restores dtype/layout;
 * this boundary rechecks dimensions and handles Bungee's edge reads and
 * overlapping synthesis pipeline without reading beyond the input buffer.
 *
 * Reads: render_contract.h, bungee/Bungee.h (vendored Basic v2.4.30).
 */

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

#include "bungee/Bungee.h"
#include "render_contract.h"

namespace nb = nanobind;
using pytimestretch::native::InputBuffer;
using pytimestretch::native::make_output;
using ControlBuffer =
    nb::ndarray<const double, nb::shape<-1, 2>, nb::c_contig, nb::device::cpu>;

#ifndef PYTIMESTRETCH_BUNGEE_SOURCE_REVISION
#define PYTIMESTRETCH_BUNGEE_SOURCE_REVISION "v2.4.30"
#endif

namespace {

double position_at(const ControlBuffer &points, double output_frame) {
    const size_t count = points.shape(0);
    if (output_frame <= 0.0) return points(0, 1);
    if (output_frame >= points(count - 1, 0)) return points(count - 1, 1);

    // The grain iterator visits points in order. A binary search avoids a
    // full marker scan on each grain when a caller supplies dense automation.
    size_t low = 1;
    size_t high = count - 1;
    while (low < high) {
        const size_t mid = low + (high - low) / 2;
        if (points(mid, 0) < output_frame) low = mid + 1;
        else high = mid;
    }
    const double left_output = points(low - 1, 0);
    const double right_output = points(low, 0);
    const double fraction = (output_frame - left_output) / (right_output - left_output);
    return points(low - 1, 1) + fraction * (points(low, 1) - points(low - 1, 1));
}

struct RenderInputs {
    size_t channels;
    size_t frames;
    size_t target;
};

RenderInputs validate(const InputBuffer &buffer, int sample_rate,
                      const ControlBuffer &points, double pitch_scale) {
    const size_t channels = buffer.shape(0);
    const size_t frames = buffer.shape(1);
    if (channels < 1 || channels > 2 || frames < 1 ||
        frames > static_cast<size_t>(std::numeric_limits<int>::max() / 2)) {
        throw std::invalid_argument("bungee: expected mono/stereo audio with a supported frame count");
    }
    if (sample_rate < 8000 || sample_rate > 192000) {
        throw std::invalid_argument("bungee: sample_rate must be within 8000..192000 Hz");
    }
    if (!std::isfinite(pitch_scale) || pitch_scale < 0.25 || pitch_scale > 4.0) {
        throw std::invalid_argument("bungee: pitch_scale must be within 0.25..4.0");
    }
    if (points.shape(0) < 2 || points(0, 0) != 0.0) {
        throw std::invalid_argument("bungee: control_points must start at output frame 0 and have at least 2 rows");
    }
    double previous_output = -1.0;
    for (size_t i = 0; i < points.shape(0); ++i) {
        const double output = points(i, 0);
        const double source = points(i, 1);
        if (!std::isfinite(output) || output != std::floor(output) ||
            output <= previous_output || output > 9007199254740992.0 ||
            !std::isfinite(source) || source < 0.0 || source > static_cast<double>(frames)) {
            throw std::invalid_argument("bungee: invalid control_points");
        }
        previous_output = output;
    }
    if (previous_output >
        static_cast<double>(std::numeric_limits<size_t>::max() / channels / sizeof(float))) {
        throw std::overflow_error("bungee: output would be too large");
    }
    return {channels, frames, static_cast<size_t>(previous_output)};
}

void render_into(float *output, const InputBuffer &buffer,
                 const ControlBuffer &points, int sample_rate,
                 double pitch_scale, const RenderInputs &in) {
    Bungee::Stretcher<Bungee::Basic> stretcher({sample_rate, sample_rate},
                                              static_cast<int>(in.channels));
    const int max_input = stretcher.maxInputFrameCount();
    if (max_input < 1 || max_input > std::numeric_limits<int>::max() / 4) {
        throw std::runtime_error("bungee: invalid maximum input grain size");
    }
    std::vector<float> edge(in.channels * static_cast<size_t>(max_input), 0.0f);

    Bungee::Request request{};
    request.position = position_at(points, 0.0);
    request.speed = position_at(points, 1.0) - request.position;
    request.pitch = pitch_scale;
    request.reset = true;
    request.resampleMode = resampleMode_autoOut;
    stretcher.preroll(request);

    size_t produced = 0;
    size_t hop = 0;
    // Each valid grain emits at least one frame. Allow extra iterations for
    // preroll; zero-output loops otherwise fail rather than hanging forever.
    const size_t max_grains = in.target + 64;
    for (size_t grain = 0; produced < in.target && grain < max_grains; ++grain) {
        const Bungee::InputChunk input_chunk = stretcher.specifyGrain(request);
        const int64_t begin = input_chunk.begin;
        const int64_t end = input_chunk.end;
        const int64_t chunk_size = end - begin;
        if (chunk_size < 0 || chunk_size > max_input) {
            throw std::runtime_error("bungee: invalid input grain range");
        }

        const float *data = nullptr;
        intptr_t stride = 0;
        if (begin >= 0 && end <= static_cast<int64_t>(in.frames)) {
            data = buffer.data() + begin;
            stride = static_cast<intptr_t>(in.frames);
        } else {
            std::fill(edge.begin(), edge.end(), 0.0f);
            const int64_t valid_begin = std::max<int64_t>(begin, 0);
            const int64_t valid_end = std::min<int64_t>(end, in.frames);
            if (valid_end > valid_begin) {
                for (size_t channel = 0; channel < in.channels; ++channel) {
                    std::copy_n(buffer.data() + channel * in.frames + valid_begin,
                                valid_end - valid_begin,
                                edge.data() + channel * max_input + (valid_begin - begin));
                }
            }
            data = edge.data();
            stride = max_input;
        }
        stretcher.analyseGrain(data, stride);

        Bungee::OutputChunk output_chunk{};
        stretcher.synthesiseGrain(output_chunk);
        if (output_chunk.frameCount < 0 ||
            (output_chunk.frameCount > 0 &&
             (output_chunk.data == nullptr || output_chunk.channelStride < output_chunk.frameCount))) {
            throw std::runtime_error("bungee: invalid output grain");
        }
        const size_t count = static_cast<size_t>(output_chunk.frameCount);
        if (count > 0) {
            if (hop == 0) hop = count;
            const size_t copied = std::min(count, in.target - produced);
            for (size_t channel = 0; channel < in.channels; ++channel) {
                std::copy_n(output_chunk.data + channel * output_chunk.channelStride,
                            copied, output + channel * in.target + produced);
            }
            produced += copied;
        }

        // Bungee's overlap-add output lags the requested source position by
        // roughly two synthesis hops (measured with isolated impulses in the
        // disposable harness). Query ahead so position points land on the
        // requested output timeline. Rechecked by engine alignment tests.
        const double next_output = static_cast<double>(produced + 2 * hop);
        request.position = position_at(points, next_output);
        request.speed = position_at(points, next_output + 1.0) - request.position;
        request.reset = false;
    }
    if (produced != in.target) {
        throw std::runtime_error("bungee: render ended before requested output length");
    }
    if (!std::all_of(output, output + in.channels * in.target,
                     [](float sample) { return std::isfinite(sample); })) {
        throw std::runtime_error("bungee: output contains NaN or infinity");
    }
}

nb::ndarray<nb::numpy, float, nb::ndim<2>> render(
    InputBuffer buffer, int sample_rate, ControlBuffer control_points,
    double pitch_scale) {
    const RenderInputs in = validate(buffer, sample_rate, control_points, pitch_scale);
    auto output = make_output(in.channels, in.target);
    {
        nb::gil_scoped_release release;
        render_into(output.data(), buffer, control_points, sample_rate,
                    pitch_scale, in);
    }
    return output;
}

nb::dict engine_info() {
    nb::dict info;
    info["engine"] = "bungee";
    info["edition"] = Bungee::Stretcher<Bungee::Basic>::edition();
    info["version"] = Bungee::Stretcher<Bungee::Basic>::version();
    info["source_revision"] = PYTIMESTRETCH_BUNGEE_SOURCE_REVISION;
    info["fft"] = "PFFFT";
    return info;
}

}  // namespace

NB_MODULE(_bungee, m) {
    m.doc() = "Native Bungee Basic binding for offline source-position curves.";
    m.def("render", &render, nb::arg("buffer"), nb::arg("sample_rate"),
          nb::arg("control_points"), nb::arg("pitch_scale"));
    m.def("engine_info", &engine_info, "Report the compiled Bungee Basic build.");
}
