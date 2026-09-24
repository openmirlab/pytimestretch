"""Future backend-neutral time-stretch entry point.

This module deliberately contains no engine adapter yet. The proposed audio
contract and backend acceptance checks live in the package thought; keeping
the stub loud prevents a scaffold import from masquerading as working DSP.

Reads: nothing internal.
"""


def stretch_audio(
    audio: object,
    *,
    sample_rate: int,
    duration_ratio: float,
    backend: str = "rubberband",
) -> object:
    """Stretch audio; implementation pending backend contract verification."""
    raise NotImplementedError(
        "pytimestretch is a package scaffold; no audio backend is implemented yet"
    )
