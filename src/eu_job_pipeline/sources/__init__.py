"""Job sources. Each one turns a public jobs API into normalised `Job` records."""

from .arbeitnow import ArbeitnowSource
from .base import JobSource, make_client
from .bundesagentur import BundesagenturSource
from .greenhouse import GreenhouseSource
from .lever import LeverSource

__all__ = [
    "ArbeitnowSource",
    "BundesagenturSource",
    "GreenhouseSource",
    "JobSource",
    "LeverSource",
    "make_client",
]
