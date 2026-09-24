/**
 * render_contract.h — shared native contract v2 plumbing for both bindings.
 *
 * Header-only; owns what rubberband_module.cpp and signalsmith_module.cpp
 * both duplicated: the nanobind buffer typedefs, the common input checks
 * every render()/_stretch_diagnostics() call shares, channel pointer
 * extraction, and the capsule-owned output allocation. Each module still
 * owns its own engine-specific validation (key-frame maps, Signalsmith's
 * own checks) and calls validate_common() as part of building its own
 * RenderInputs.
 *
 * Reads: nanobind/nanobind.h, nanobind/ndarray.h.
 */

#pragma once

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace pytimestretch::native {

namespace nb = nanobind;

using InputBuffer =
    nb::ndarray<const float, nb::ndim<2>, nb::c_contig, nb::device::cpu>;

// Native contract v2's marker array: int64 (K, 2) rows of
// (source_frame, output_frame), C-contiguous. The facade guarantees the
// invariants (first row (0, 0), last row (frames, target), both columns
// strictly increasing, K >= 2); each binding re-derives frames/target from
// the last row and still checks frames against the buffer, rather than
// trusting the facade blindly.
using MarkersBuffer =
    nb::ndarray<const int64_t, nb::shape<-1, 2>, nb::c_contig, nb::device::cpu>;

/** The subset of contract v2's validated inputs that both engines derive
 * identically. Each module's own RenderInputs adds its engine-specific
 * fields (Rubber Band: options/key_frame_map; Signalsmith: the raw marker
 * list) around this. */
struct CommonRenderInputs {
    size_t channels;
    size_t frames;
    size_t target_frames;
};

/**
 * Validate the input shared by render()/_stretch_diagnostics() on both
 * bindings: buffer shape, sample_rate, marker count/shape, and pitch_scale
 * -- in that order, matching rubberband_module.cpp's original
 * validate_render(). `engine` ("rubberband"/"signalsmith") prefixes every
 * message, matching each module's own error text exactly. Does not
 * validate `quality`; each engine resolves that name itself (Rubber Band
 * maps it to engine/window options as part of validation, Signalsmith
 * resolves it later in configure_engine()), so this only checks pitch_scale
 * and leaves quality to the caller.
 */
inline CommonRenderInputs validate_common(const InputBuffer &buffer,
                                           int sample_rate,
                                           const MarkersBuffer &markers,
                                           double pitch_scale,
                                           const char *engine) {
    std::string prefix = std::string(engine) + ": ";

    size_t channels = buffer.shape(0);
    size_t frames = buffer.shape(1);
    if (channels < 1 || frames < 1) {
        throw std::runtime_error(
            prefix + "buffer must have at least one channel and frame, "
            "got shape (" +
            std::to_string(channels) + ", " + std::to_string(frames) + ")");
    }
    if (sample_rate <= 0) {
        throw std::runtime_error(prefix + "sample_rate must be > 0, got " +
                                  std::to_string(sample_rate));
    }

    size_t k = markers.shape(0);
    if (k < 2) {
        throw std::runtime_error(prefix + "markers must have at least 2 rows, got " +
                                  std::to_string(k));
    }

    int64_t marker_frames = markers(k - 1, 0);
    int64_t marker_target = markers(k - 1, 1);
    if (marker_frames < 0 || static_cast<size_t>(marker_frames) != frames) {
        throw std::runtime_error(
            prefix + "markers[-1][0] (" + std::to_string(marker_frames) +
            ") must equal the buffer's frame count (" +
            std::to_string(frames) + ")");
    }
    if (marker_target < 1) {
        throw std::runtime_error(prefix + "markers[-1][1] must be >= 1, got " +
                                  std::to_string(marker_target));
    }

    if (!std::isfinite(pitch_scale) || pitch_scale <= 0.0) {
        throw std::runtime_error(prefix + "pitch_scale must be finite and > 0, got " +
                                  std::to_string(pitch_scale));
    }

    CommonRenderInputs in;
    in.channels = channels;
    in.frames = frames;
    in.target_frames = static_cast<size_t>(marker_target);
    return in;
}

/** `buffer.data() + c * frames` for every channel `c` -- both bindings' own
 * copy of this was identical. */
inline std::vector<const float *> channel_pointers(const InputBuffer &buffer,
                                                     size_t channels,
                                                     size_t frames) {
    std::vector<const float *> ptrs(channels);
    for (size_t c = 0; c < channels; ++c) {
        ptrs[c] = buffer.data() + c * frames;
    }
    return ptrs;
}

/** Allocate an owned, C-contiguous float32 (channels, target_frames)
 * buffer and wrap it as a capsule-owned ndarray, per both bindings'
 * render(). Must run before any nb::gil_scoped_release (capsule creation
 * touches Python); callers write into the returned array's .data() with
 * the GIL released, then return the array. `new float[n]` matches both
 * modules' prior behavior (uninitialized, not zero-init) since both fully
 * overwrite every element before returning. */
inline nb::ndarray<nb::numpy, float, nb::ndim<2>> make_output(size_t channels,
                                                                size_t target_frames) {
    float *data = new float[channels * target_frames];
    nb::capsule owner(data, [](void *p) noexcept { delete[] static_cast<float *>(p); });
    size_t shape[2] = {channels, target_frames};
    return nb::ndarray<nb::numpy, float, nb::ndim<2>>(data, 2, shape, owner);
}

}  // namespace pytimestretch::native
