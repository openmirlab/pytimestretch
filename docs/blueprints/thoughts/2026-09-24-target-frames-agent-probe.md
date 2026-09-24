# target_frames agent probe

> 2026-09-24 · This evidence feeds the public-API decision back to Paul. Verdict: do not add `target_frames=`; document the `duration_ratio = target / len(audio)` idiom instead. The disposable harness and agent solutions live in the session scratchpad, not in this repository.

## Question and pre-registered rule

Does offering an either-or `target_frames=` next to `duration_ratio=` in
`time_stretch(audio, sample_rate, *, duration_ratio=...)` make coding agents
write more correct length-targeted stretch code? Agents are fluent in plain
Python/NumPy/SciPy and carry pyrubberband/librosa priors (`rate > 1` means
faster; librosa arrays are channels-first).

Rule, stated before the first trial: on the length-targeted tasks (T1–T3),
add `target_frames` if arm B beats arm A by at least 20 percentage points;
under 10 points, do not add it and document the ratio idiom; 10–20 points is
inconclusive and also means no new parameter. If arm B lost two or more T4
(ratio-natural control) trials, count that as a cost.

## Method

- Two arms, one variable: identical API documentation, except arm B's
  signature and one paragraph add `target_frames` ("pass exactly one").
- Six `sonnet` agents per arm; each saw only the documentation in its prompt,
  wrote one module implementing five functions in one shot, and could not run
  code or read the repository.
- Scoring ran every function against a mock `pytimestretch` that applied the
  contract's validation and length rule (linear interpolation stood in for
  stretching) and compared output shapes with the known answers.
- Tasks: T1 fit a 100 BPM one-bar loop to 120 BPM (105840 → 88200 frames);
  T2 match another stereo clip's length (longer and shorter reference);
  T3 fit stereo audio to exactly 8 beats at 128, 140 (non-integer frames,
  ±1 accepted), and 90 BPM at 48 kHz; T4 half-time control; T5 librosa
  `(2, n)` audio made 1.5× longer in the same layout (observation only).

## Result

| Arm | T1–T3 (18 trials) | T4 | T5 |
| --- | ---: | ---: | ---: |
| A: `duration_ratio` only | 18/18 | 6/6 | 6/6 |
| B: plus `target_frames` | 18/18 | 6/6 | 6/6 |

Arm B agents did use the new parameter: all six called `target_frames=` for
T2 and T3, and `duration_ratio=` elsewhere. Every T5 solution transposed the
librosa array in and out correctly.

## Verdict and limits

No difference, so `target_frames` is not added. The `time_stretch` docstring
shows fitting to an exact length with `duration_ratio=target_frames / len(audio)`.

This is a ceiling result: a strong model, documentation that states the
rounding rule, clean inputs, and no chance to iterate. It shows the parameter
is unnecessary under those conditions, not that it could never help. Revisit
if Tactus agents make length-fitting errors in practice or if a weaker model
becomes the typical caller.
