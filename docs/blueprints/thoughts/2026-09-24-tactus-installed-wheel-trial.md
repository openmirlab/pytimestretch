# Tactus trial with an installed wheel

> 2026-09-24 · **Status:** measured; listening and production adoption pending · Both native backends complete the existing Tactus production without changing unrelated stems.

## Result

An isolated copy of active Tactus's `examples/real-chop-flip` runs through
the installed `tactus run` CLI with either pytimestretch backend. No Tactus
runtime, dependency declaration, accepted production, or source asset was
changed. This establishes an integration path, not sonic parity or approval
to replace the existing production.

Five runs succeeded: the existing pyrubberband baseline, the native Rubber
Band candidate, the Signalsmith candidate, a native Rubber Band candidate
with `bass_gain_db=-9.0`, and a repeat of the native Rubber Band default.
All 20 delivered WAVs are finite, within full scale, PCM24 stereo at
44.1 kHz, and exactly 984,900 frames (eight bars at 90 BPM plus a one-second
authored tail). Their file hashes match the manifests.

- Both native candidates preserve the baseline's drum and bass WAV hashes.
- The bass parameter candidate preserves the native default's sample and
  drum WAV hashes; only bass and mix change.
- Repeating the native Rubber Band default reproduces all four WAV hashes.
- The original example's four Python source hashes remain unchanged.
- Sample and mix differ from the old baseline. No listening preference or
  performance comparison was established by this run.

## Environment and source identity

- pytimestretch source: `b85f982`; local wheel built through `uv build`
  (sdist to wheel), installed into a new venv rather than imported from src.
  Wheel: `pytimestretch-0.0.0-cp313-cp313-linux_x86_64.whl`;
  SHA256 `f3c4b486bac787ee0f6c067b85484fd688cbb7d99712e92c9a53e8daea81417f`.
  Only documentation and the dogfood ignore rule were pending during build.
- Tactus: local revision `9feccddef7d20f933881e2012ce4658296e06f4b`,
  package `0.1.0`; the existing unrelated working-tree note was left intact.
- Linux x86_64, CPython 3.13.5, NumPy 2.5.3, SciPy 1.18.1,
  SoundFile 0.14.0. Baseline: pyrubberband 0.4.0 and system Rubber Band 3.3.0.
- Native Rubber Band: v4.0.0 / offline R3,
  `1d95888bec3ae0a17c0c4af791810d5a63f6bc35`, built-in FFT, BQResampler.
- Native Signalsmith Stretch: 1.3.2,
  `57b93f4e9206a089a45387eaa39bdc9f310d3308`; Linear
  `5668673560146a9cfe38c25315071e3fd68c8317`, built-in FFT, default preset,
  seed 24301. Both candidates use `quality="high"`.
- The sdist-built wheel's `engine_info()` reports fallback revision labels
  (`v4.0.0`, `main@57b93f4`, `0.3.1`); the full SHAs above were separately
  verified with `git submodule status` in its source checkout.
- Real source: `CErZvbcaOeE_inst.wav`, SHA256
  `845406ed5823a0af0dc4eec0985a58398bda9b74310c7c9e76863e1b17db1497`;
  beat grid `CErZvbcaOeE.npy`, SHA256
  `72aacde1e3184be72ef668f9f5ed67a606e7bf40b17bf05af7c9f02fd8de0b93`.
  The production verifies both identities before reading four bars near
  54.1 seconds. Audio and sidecar remain outside Git.

The installed wheel also passes the full package suite: **319 passed**.
`uv run ruff check .` and the sdist-to-wheel build pass.

## Reproduction and evidence

Local evidence lives in the ignored `dogfood/2026-09-24-tactus-wheel/`:
`run_trial.py`, `run.log`, `evidence.json`, `installed.txt`, copied sources,
CLI responses, manifests, receipts, and audio. It is disposable evidence;
fresh clones need the separately owned audio/grid and a new trial directory.

Install the wheel, the active Tactus checkout, and `pyrubberband==0.4.0`
into a fresh CPython 3.13 venv. Copy `examples/real-chop-flip` separately for
the baseline and each candidate. Point `TACTUS_CHOP_SOURCE` and
`TACTUS_CHOP_GRID` at the pinned assets. In each candidate's `chops.py`,
replace the pyrubberband import and stretch call with:

```python
import pytimestretch

stretched = pytimestretch.time_stretch(
    audio, rate, duration_ratio=frames / len(audio), backend="rubberband"
)
```

Use `backend="signalsmith"` for the other candidate. Keep the existing
frame assertion, fades, arrangement, filters, delay, and mix unchanged.
Run each copied `song.py` with `tactus run ... --out NEW_DIRECTORY`.
Use `--params '{"bass_gain_db": -9.0}'` for the bass candidate. Compare
manifest hashes and decode each delivered WAV before judging the result.

## Friction and remaining boundary

The replacement needs an import change and a ratio inversion:
`len(audio) / frames` becomes `frames / len(audio)`. No extra Tactus core
helper was needed in this example.

Tactus's receipt explicitly excludes external processor identities and the
copied example has no dependency lock. The trial records installed versions,
wheel hash, source hashes and engine metadata in `evidence.json`; production
adoption needs equivalent attribution owned by the production. This is an
existing attribution limit, not a missing stretch API.

Listening remains open: the baseline uses a different engine revision and
configuration, so different sample/mix hashes are expected and cannot prove
either superiority or a regression. Review the actual candidate audio before
changing Tactus's accepted example or adopting pytimestretch as a dependency.
