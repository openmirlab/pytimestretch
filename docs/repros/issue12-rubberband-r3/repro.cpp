#include <rubberband/RubberBandStretcher.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <random>
#include <vector>

int main() {
    using RubberBand::RubberBandStretcher;
    constexpr int sr = 44100, length = 10 * sr, block = 256;
    std::vector<float> x(length);
    std::mt19937 rng(0);
    std::normal_distribution<float> noise(0.f, 0.002f);
    for (float &v : x) v = noise(rng);
    const double pi = std::acos(-1.0);
    for (int k = 0; k < 9; ++k) {
        int at = int(std::lround((0.6 + k) * sr));
        for (int j = 0; j < 24; ++j) {
            x[at + j] += 0.8f * (0.5f - 0.5f * std::cos(2 * pi * j / 23));
        }
    }
    auto opts = RubberBandStretcher::OptionProcessOffline |
        RubberBandStretcher::OptionThreadingNever |
        RubberBandStretcher::OptionChannelsApart |
        RubberBandStretcher::OptionEngineFiner;
    RubberBandStretcher rb(sr, 1, opts, 1.3, 1.0);
    rb.setExpectedInputDuration(length);
    rb.setMaxProcessSize(block);
    rb.setKeyFrameMap({{4 * sr, 4 * sr}, {5 * sr, 8 * sr}, {length, 13 * sr}});
    for (int pos = 0; pos < length; pos += block) {
        int n = std::min(block, length - pos);
        const float *p[1] = {x.data() + pos};
        rb.study(p, n, pos + n == length);
    }
    std::vector<float> y, buf(block);
    auto drain = [&]() {
        while (rb.available() > 0) {
            float *p[1] = {buf.data()};
            size_t n = rb.retrieve(p, std::min(block, rb.available()));
            y.insert(y.end(), buf.begin(), buf.begin() + n);
        }
    };
    for (int pos = 0; pos < length; pos += block) {
        int n = std::min(block, length - pos);
        const float *p[1] = {x.data() + pos};
        rb.process(p, n, pos + n == length);
        drain();
    }
    drain();
    std::printf("engine=%d output_frames=%zu\n", rb.getEngineVersion(), y.size());
    if (y.size() != size_t(13 * sr)) return 1;
    for (int k = 0; k < 9; ++k) {
        double t = 0.6 + k;
        double want = t < 4 ? t : t < 5 ? 4 + (t - 4) * 4 : t + 3;
        int a = int(std::lround((want - 0.45) * sr));
        int b = std::min(int(y.size()), int(std::lround((want + 0.45) * sr)));
        int peak = a;
        for (int i = a + 1; i < b; ++i) if (std::abs(y[i]) > std::abs(y[peak])) peak = i;
        std::printf("input=%.1f expected=%.1f error_ms=%+.2f\n", t, want, 1000 * (double(peak) / sr - want));
    }
}
