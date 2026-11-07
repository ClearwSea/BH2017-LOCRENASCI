"""Compatibility entry for python -m packager from the repository root."""
from pathlib import Path
import sys
_source = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_source))
__path__ = [str(_source / "packager")]
from .version import __version__
