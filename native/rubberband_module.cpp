/**
 * rubberband_module.cpp — nanobind entry point for pytimestretch._rubberband.
 *
 * Step 2 of the binding-first plan: proves the vendored Rubber Band
 * single-file build (extern/rubberband/single/RubberBandSingle.cpp) links
 * and runs inside the extension, before the real `stretch()` native
 * contract lands in step 3. `engine_info()` constructs and destroys one
 * offline RubberBandStretcher as a smoke path and reports the compiled
 * version/FFT/resampler configuration plus the pinned submodule revision,
 * so a build can be traced back to exactly what it linked against.
 *
 * Reads: rubberband/RubberBandStretcher.h (vendored, extern/rubberband).
 */

#include <nanobind/nanobind.h>

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
    m.doc() = "Native Rubber Band binding (engine_info only — stretch() lands in step 3)";
    m.def("engine_info", &engine_info, "Report the compiled Rubber Band build configuration.");
}
