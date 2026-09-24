# Blind listening — round 2

> 2026-09-25 · Paul's blind judgments on real loops for the warp/pitch/quality plan. Rubber Band high won every cell where Paul heard a difference; formant preservation clearly helped the vocal; `quality="fast"` (R2) brought no audible benefit and was worst on the bass pitch shift. Evidence for the decisions on `quality` levels, warp default, and formant defaults.

## Setup

- Material: four commercial loops from rytho-library, used locally only
  (never committed or published): a 100 BPM drum loop (48 kHz, 4 bars), a
  96 BPM full-mix loop (4 bars), the first 4 bars of an 85 BPM vocal lead,
  and the first 4 bars of a 124 BPM bassline; all stereo, 44.1/48 kHz.
- Build: HEAD `9ab16ba`; Rubber Band v4.0.0, Signalsmith Stretch 1.3.2 +
  main@57b93f4.
- Per-cell RMS level matching (−1 dBFS peak ceiling), 10 ms fades, labels
  randomly permuted per cell, key hidden until every cell was answered,
  unprocessed excerpt available as reference.

## Judgments

| Cell | Task | Candidates | Best | Worst | Paul's notes |
| --- | --- | --- | --- | --- | --- |
| 1 | drum loop warped to ~67 % swing (65 markers, local ratio 0.67–1.33) | rb high, rb fast, ss high | **rb high** | ss high | worst "sounds a bit smeared on the hits" |
| 2 | full mix 96 → 120 BPM | rb high/balanced/fast, ss high/balanced | none | none | no audible difference |
| 3 | vocal +3 semitones | rb high shift/preserve, ss high shift/preserve | **rb preserve** | rb shift | both *preserve* versions better; both *shift* versions "brighter and flatter", worse timbre |
| 4 | bass −5 semitones | rb high, rb fast, ss high | **rb high** | rb fast | worst "muddy"; rb high and ss high close |

## Reading

- **Default engine.** Rubber Band high remains the best default for warp and
  pitch shifting. Signalsmith was close on the bass but worst on the warped
  drums.
- **Measured vs heard warp placement.** On the humanized-grid click test,
  Rubber Band R3 peaks landed up to 20–33 ms off under ±20 % local ratio
  changes, yet on a real drum loop with ±33 % local changes it was judged
  best. Peak position of a smeared click overstates audible misalignment;
  the click-train numbers stay as regression pins, not as a quality
  ranking.
- **`quality="fast"` (R2).** Indistinguishable on the full-mix tempo change
  (as was `"balanced"`), middle on the warp, and worst on the bass pitch
  shift, where it is also measurably flat (−31 cents at −5 semitones). Its
  tighter click placement did not translate into a preference.
- **`quality="balanced"`.** Indistinguishable from `"high"` on the full-mix
  tempo change at ~3× (Rubber Band) / ~1.7× (Signalsmith) the speed.
- **Formants.** Preservation is clearly preferable for a vocal on both
  engines. Not tested on instruments.

## Limits

One listener, one loop per cell, one ratio or shift per task. Cell 2 shows
that moderate tempo changes on dense mixes hide engine differences; extreme
ratios were covered only in round 1.
