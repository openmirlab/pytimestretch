"""Early package facade; audio processing is not implemented yet."""

from .__about__ import __version__
from .stretch import stretch_audio

__all__ = ["__version__", "stretch_audio"]
