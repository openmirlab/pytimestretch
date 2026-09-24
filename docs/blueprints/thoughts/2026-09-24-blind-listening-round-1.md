# Blind listening — round 1

> 2026-09-24 · Paul's blind judgments of the two direct bindings and the first Python/Numba prototype. Rubber Band (R3) was judged best in all six cells. This is one listener on two short mono excerpts; Paul found the material too limited to hear differences well, so round 2 uses real loops from rytho-library.

## Setup

- Sources: the first probe's 4-second mono beat and pad excerpts, 44.1 kHz.
- Ratios: ×0.5, ×1.5, ×3.0 (six cells).
- Candidates per cell: Rubber Band v4.0.0 direct binding (R3, offline),
  Signalsmith Stretch 1.3.2 direct binding (`.exact()`), and the first
  probe's Python/Numba phase vocoder.
- Per-cell RMS level matching (peak ceiling −1 dBFS), 10 ms fades, labels
  A/B/C randomly permuted per cell with a fixed seed; the key stayed outside
  the served page until every cell was answered. The unstretched source was
  available as a reference in each cell.

## Judgments

| Cell | Best | Worst |
| --- | --- | --- |
| beat ×0.5 | Rubber Band | Python prototype |
| beat ×1.5 | Rubber Band | Python prototype |
| beat ×3.0 | Rubber Band | Signalsmith |
| pad ×0.5 | Rubber Band | Python prototype |
| pad ×1.5 | Rubber Band | Python prototype |
| pad ×3.0 | Rubber Band | Signalsmith |

No notes were written.

## Reading

- Rubber Band's lead is consistent across both sources and all ratios, which
  supports keeping it the default backend. Its ~13 ms early impulse peak at
  ×3.0 did not cost it the beat ×3.0 cell.
- Signalsmith was worst in both ×3.0 cells, consistent with its upstream
  README's note that stretching sounds best between about 0.75× and 1.5×.
  It never won a cell.
- The Python prototype was worst in the other four cells. This prototype is
  not a candidate for everyday stretching; the Python lane continues only if
  a concrete creative-control task justifies it.

## Limits and next round

One listener, two 4-second mono excerpts, no stereo, voice, or mixed music.
Paul judged this material too limited. Round 2 uses loops from rytho-library,
with stereo material, so the `ChannelsApart` vs `ChannelsTogether` question
can be heard too.
