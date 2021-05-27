"""Top-level package for TensorFlow PhaseSpace."""
from pkg_resources import get_distribution

__author__ = """Albert Puig Navarro"""
__email__ = "apuignav@gmail.com"
__version__ = get_distribution(__name__).version
__maintainer__ = "zfit"

__credits__ = [
    "Jonas Eschle <Jonas.Eschle@cern.ch>",
]

__all__ = [
    "GenParticle",
    "nbody_decay",
    "random",
]

from . import random
from .phasespace import GenParticle, nbody_decay
