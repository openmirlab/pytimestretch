# Rubber Band R3 keyframe placement: standalone reproduction

This is a source-level reproduction for [pytimestretch issue #12](https://github.com/openmirlab/pytimestretch/issues/12). It calls Rubber Band v4.0.0 directly, without Python or the pytimestretch binding, using the same offline two-pass setup and 256-frame processing blocks. The input is ten seconds of low noise with nine short clicks. The keyframe map makes source seconds 4–5 occupy output seconds 4–8.

From the repository root, compile and run:

```sh
g++ -std=c++17 -O2 -I extern/rubberband \
  docs/repros/issue12-rubberband-r3/repro.cpp \
  extern/rubberband/single/RubberBandSingle.cpp \
  -o /tmp/pytimestretch-r3-keyframe-repro -pthread
/tmp/pytimestretch-r3-keyframe-repro
```

On the pinned v4.0.0 engine (`extern/rubberband` revision `1d95888`), the program reports 573300 output frames, exactly the requested length. Clicks before the local stretch are within 0.3 ms of their target. The click at source 4.6 s is about **32 ms early**, and every later click is about **13 ms early**. A separate run with the installed Rubber Band v3.3.0 command-line tool and the same time map also misplaced the inside click (about 67 ms early). The difference between those two magnitudes reflects different engine versions and processing blocks; both runs show that the error exists without the pytimestretch binding.

The output length therefore does not establish that individual transients follow the keyframe curve. This reproducer does not identify an engine patch or establish an error bound for other audio. The default Bungee `time_warp` path and the corrected Signalsmith path remain the practical marker-alignment choices while this R3 limitation is open.
